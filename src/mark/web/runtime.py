"""Web runtime: per-thread App instances, the event bus, and the job manager.

SQLite connections aren't shareable across threads, so the web layer hands out
one App per thread (FastAPI runs sync endpoints in a thread pool). Long-running
work (generate, post, learn, ...) runs as tracked background jobs that publish
progress over the event bus; the UI subscribes via SSE.
"""

from __future__ import annotations

import queue
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from ..app import App, get_app
from ..llm import LLM


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
# Event bus (SSE fan-out)
# --------------------------------------------------------------------------- #
class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=500)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, kind: str, data: dict) -> None:
        event = {"kind": kind, "ts": _now(), **data}
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass  # slow consumer; drop rather than block the pipeline


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
class Job:
    def __init__(self, kind: str, label: str, product_id: Optional[str] = None):
        self.id = uuid.uuid4().hex[:10]
        self.kind = kind
        self.label = label
        self.product_id = product_id
        self.status = "queued"          # queued | running | done | failed
        self.progress = 0.0             # 0..1
        self.message = ""
        self.result: Any = None
        self.error: Optional[str] = None
        self.created_at = _now()
        self.finished_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "label": self.label,
            "product_id": self.product_id, "status": self.status,
            "progress": round(self.progress, 3), "message": self.message,
            "result": self.result, "error": self.error,
            "created_at": self.created_at, "finished_at": self.finished_at,
        }


class JobManager:
    """Runs engine work in background threads and tracks progress.

    Each job function receives (app, llm, job, report) where `report(progress,
    message)` updates state and publishes an event.
    """

    MAX_JOBS_KEPT = 200

    def __init__(self, runtime: "Runtime", bus: EventBus, workers: int = 3):
        self.runtime = runtime
        self.bus = bus
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mark-job")
        self.jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()

    def submit(self, kind: str, label: str,
               fn: Callable[[App, LLM, Job, Callable], Any],
               product_id: Optional[str] = None) -> Job:
        job = Job(kind, label, product_id)
        with self._lock:
            self.jobs[job.id] = job
            self._order.append(job.id)
            while len(self._order) > self.MAX_JOBS_KEPT:
                self.jobs.pop(self._order.pop(0), None)
        self.bus.publish("job", job.to_dict())

        def _run() -> None:
            app = self.runtime.fresh_app()
            llm = LLM(app)
            job.status = "running"
            self.bus.publish("job", job.to_dict())

            def report(progress: float, message: str = "") -> None:
                job.progress = max(job.progress, min(progress, 1.0))
                if message:
                    job.message = message
                self.bus.publish("job", job.to_dict())

            try:
                job.result = fn(app, llm, job, report)
                job.status = "done"
                job.progress = 1.0
            except Exception as exc:  # noqa: BLE001 - jobs must surface, not crash
                job.status = "failed"
                job.error = f"{exc}"
                traceback.print_exc()
            finally:
                job.finished_at = _now()
                self.bus.publish("job", job.to_dict())
                app.close()

        self.executor.submit(_run)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def recent(self, limit: int = 25) -> list[dict]:
        with self._lock:
            ids = list(reversed(self._order[-limit:]))
        return [self.jobs[i].to_dict() for i in ids if i in self.jobs]

    def has_running(self, kind: Optional[str] = None) -> bool:
        return any(j.status in ("queued", "running")
                   and (kind is None or j.kind == kind)
                   for j in self.jobs.values())


# --------------------------------------------------------------------------- #
# Autopilot (background scheduler wrapper)
# --------------------------------------------------------------------------- #
class Autopilot:
    def __init__(self, runtime: "Runtime", bus: EventBus):
        self.runtime = runtime
        self.bus = bus
        self._sched = None
        self._lock = threading.Lock()
        self.started_at: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._sched is not None and getattr(self._sched, "running", False)

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            from ..scheduler import engine

            app = self.runtime.fresh_app()
            llm = LLM(app)
            self._sched = engine.build_scheduler(
                app, llm, blocking=False, app_factory=self.runtime.fresh_app)
            self._sched.start()
            self.started_at = _now()
            from .. import db as db_module

            db_module.log_activity(app.conn, "autopilot", "Autopilot started", level="success")
            self.bus.publish("autopilot", {"running": True})

    def stop(self) -> None:
        with self._lock:
            was_running = self._sched is not None
            if self._sched is not None:
                try:
                    self._sched.shutdown(wait=False)
                except Exception:
                    pass
                self._sched = None
            self.started_at = None
            if not was_running:
                return  # idempotent shutdown — don't spam the activity feed
            app = self.runtime.fresh_app()
            from .. import db as db_module

            db_module.log_activity(app.conn, "autopilot", "Autopilot stopped")
            app.close()
            self.bus.publish("autopilot", {"running": False})

    def upcoming(self, limit: int = 20) -> list[dict]:
        if self._sched is not None:
            from datetime import datetime as dt

            out = []
            for job in self._sched.get_jobs():
                nxt = getattr(job, "next_run_time", None)
                out.append({"id": job.id, "name": job.name,
                            "next": nxt.strftime("%Y-%m-%d %H:%M") if nxt else "—"})
            out.sort(key=lambda x: x["next"])
            return out[:limit]
        # Not running — compute what the schedule would be.
        from ..scheduler import engine

        app = self.runtime.fresh_app()
        try:
            return engine.upcoming(app, LLM(app), limit=limit)
        finally:
            app.close()


# --------------------------------------------------------------------------- #
# Runtime — the single object the API layer talks to
# --------------------------------------------------------------------------- #
class Runtime:
    def __init__(self, home: Optional[Path] = None, force_mock: bool = False):
        self.home = home
        self.force_mock = force_mock
        self._local = threading.local()
        self._generation = 0
        self.bus = EventBus()
        self.jobs = JobManager(self, self.bus)
        self.autopilot = Autopilot(self, self.bus)

    def fresh_app(self) -> App:
        return get_app(home=self.home, force_mock=self.force_mock)

    def app(self) -> App:
        """Per-thread App, rebuilt after settings changes (reload())."""
        cached = getattr(self._local, "app", None)
        if cached is None or getattr(self._local, "gen", -1) != self._generation:
            if cached is not None:
                cached.close()
            self._local.app = self.fresh_app()
            self._local.gen = self._generation
        return self._local.app

    def llm(self) -> LLM:
        return LLM(self.app())

    def reload(self) -> None:
        """Invalidate cached per-thread Apps (after settings/YAML changes)."""
        self._generation += 1

    def shutdown(self) -> None:
        self.autopilot.stop()
        self.jobs.executor.shutdown(wait=False, cancel_futures=True)
