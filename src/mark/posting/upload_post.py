"""upload-post.com client — one API for posting across all social platforms.

Real path uses upload-post.com's REST API over httpx (no hard dependency on their
SDK). Offline path returns deterministic synthetic responses so the posting flow
can be exercised end-to-end without an account.

Every method returns a normalized dict::

    {"request_id": str, "results": {platform: {"post_id": str|None, "status": str}}}
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from ..app import App
from ..llm import _retry, log_external_cost

BASE_URL = "https://api.upload-post.com/api"

# Map Mark's platform names to upload-post's, if they ever diverge.
PLATFORM_MAP = {"x": "x"}


def _ext_platform(p: str) -> str:
    return PLATFORM_MAP.get(p, p)


class UploadPostClient:
    def __init__(self, app: App):
        self.app = app
        self.key = app.keys.upload_post
        self.user = app.settings.upload_post.profile_username

    @property
    def mock(self) -> bool:
        return self.app.is_mock("upload_post")

    # -- public API ------------------------------------------------------- #
    def upload_video(self, video_path: str, title: str, platforms: list[str],
                     *, first_comment: Optional[str] = None, **extra) -> dict:
        if self.mock:
            return self._mock_response(platforms, kind="video")
        data = {"title": title, "user": self.user}
        if first_comment:
            data["first_comment"] = first_comment
        if "tiktok" in platforms:
            data["tiktokPrivacyLevel"] = extra.get(
                "tiktok_privacy", self.app.settings.platform("tiktok").privacy_level
                or "PUBLIC_TO_EVERYONE")
        files = {"video": (Path(video_path).name, open(video_path, "rb"))}
        return self._post("/upload", data, platforms, files=files)

    def upload_photo(self, photo_paths: list[str], title: str, platforms: list[str],
                     *, first_comment: Optional[str] = None, **extra) -> dict:
        if self.mock:
            return self._mock_response(platforms, kind="photo")
        data = {"title": title, "user": self.user}
        if first_comment:
            data["first_comment"] = first_comment
        files = [("photos[]", (Path(p).name, open(p, "rb"))) for p in photo_paths]
        return self._post("/upload_photos", data, platforms, files=files)

    def upload_text(self, text: str, platforms: list[str],
                    *, first_comment: Optional[str] = None, **extra) -> dict:
        if self.mock:
            return self._mock_response(platforms, kind="text")
        data = {"title": text, "user": self.user}
        if first_comment:
            data["first_comment"] = first_comment
        return self._post("/upload_text", data, platforms)

    def post_analytics(self, request_id: str) -> dict:
        if self.mock:
            return {"request_id": request_id, "mock": True}
        return self._get(f"/uploadposts/post-analytics/{request_id}")

    def total_impressions(self) -> dict:
        if self.mock:
            return {"profile": self.user, "mock": True}
        return self._get(f"/uploadposts/total-impressions/{self.user}")

    # -- transport -------------------------------------------------------- #
    def _headers(self) -> dict:
        return {"Authorization": f"Apikey {self.key}"}

    def _post(self, path: str, data: dict, platforms: list[str], files=None) -> dict:
        import httpx

        # upload-post expects repeated platform[] fields.
        form = list(data.items()) + [("platform[]", _ext_platform(p)) for p in platforms]

        def _call():
            with httpx.Client(timeout=120) as client:
                resp = client.post(BASE_URL + path, headers=self._headers(),
                                   data=form, files=files)
                resp.raise_for_status()
                return resp.json()

        try:
            raw = _retry(_call)
        finally:
            _close_files(files)
        log_external_cost(self.app, "upload_post", "post", path, units=len(platforms))
        return _normalize(raw, platforms)

    def _get(self, path: str) -> dict:
        import httpx

        def _call():
            with httpx.Client(timeout=60) as client:
                resp = client.get(BASE_URL + path, headers=self._headers())
                resp.raise_for_status()
                return resp.json()

        return _retry(_call)

    # -- offline ---------------------------------------------------------- #
    def _mock_response(self, platforms: list[str], kind: str) -> dict:
        rid = f"mock-{uuid.uuid4().hex[:12]}"
        log_external_cost(self.app, "upload_post", "post", kind,
                          units=len(platforms), mocked=True)
        return {
            "request_id": rid,
            "results": {p: {"post_id": f"mock_{p}_{uuid.uuid4().hex[:8]}",
                            "status": "success"} for p in platforms},
        }


def _close_files(files) -> None:
    if not files:
        return
    items = files.items() if isinstance(files, dict) else files
    for _, payload in items:
        try:
            payload[1].close()
        except Exception:
            pass


def _normalize(raw: dict, platforms: list[str]) -> dict:
    """Defensively map upload-post's response into our normalized shape."""
    request_id = (raw.get("request_id") or raw.get("requestId")
                  or raw.get("id") or f"up-{uuid.uuid4().hex[:10]}")
    results = {}
    raw_results = raw.get("results") or raw.get("platforms") or {}
    for p in platforms:
        entry = raw_results.get(p) or raw_results.get(_ext_platform(p)) or {}
        if isinstance(entry, dict):
            post_id = (entry.get("post_id") or entry.get("id")
                       or entry.get("platform_post_id"))
            status = entry.get("status", "success")
        else:
            post_id, status = None, "success"
        results[p] = {"post_id": post_id, "status": status}
    return {"request_id": str(request_id), "results": results, "raw": raw}
