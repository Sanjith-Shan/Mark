"""Owner-taste learning loop: reviews → bandit reward + taste lessons +
creative experiments, end to end in offline mode.

Covers the full mobile-review contract: the feed, the submit endpoint (rating /
feedback / approve / reject / watch telemetry), the learn job, prompt
injection, experiment assignment + deterministic conclusion, and the Taste
dashboard payload.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mark import db as db_module
from mark import pipeline, scientist, store, taste
from mark.schemas import ExperimentProposal, ExperimentVariant
from mark.web.server import create_app

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Unit-ish: taste module against the app fixture
# --------------------------------------------------------------------------- #
def test_rating_reward_scale():
    assert taste.rating_reward(1) == 0.0
    assert taste.rating_reward(10) == 1.0
    assert abs(taste.rating_reward(5) - 4 / 9) < 1e-9
    assert taste.rating_reward(99) == 1.0  # clamped


def test_record_review_upserts_and_flags_first_rating(app, llm, product):
    row = pipeline.generate_one(app, llm, product, "instagram")
    review, first = taste.record_review(app, row, rating=8, feedback="love the hook")
    assert first and review["rating"] == 8
    # Re-rate: not "first" anymore; feedback appends; watch stats keep maxima.
    review, first = taste.record_review(app, row, rating=6, feedback="on second look, slower",
                                        watch_seconds=12.5, video_duration=20.0)
    assert not first
    assert review["rating"] == 6
    assert "love the hook" in review["feedback"] and "slower" in review["feedback"]
    review, _ = taste.record_review(app, row, watch_seconds=3.0)
    assert review["watch_seconds"] == 12.5  # never regresses


def test_record_review_concurrent_first_rating_claimed_once(app, llm, product):
    """Two simultaneous rating submissions (double-tap / telemetry race) must
    yield exactly ONE first_rating=True — the exactly-once bandit-credit gate."""
    import threading

    from mark.app import get_app

    row = pipeline.generate_one(app, llm, product, "x")
    results: list[bool] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def worker():
        a2 = get_app(home=app.paths.home, force_mock=True)
        try:
            barrier.wait()
            _, first = taste.record_review(a2, row, rating=7)
            results.append(first)
        except Exception as exc:  # noqa: BLE001 - the race must not 500 either
            errors.append(exc)
        finally:
            a2.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"concurrent submission raised: {errors}"
    assert results.count(True) == 1, f"first_rating claimed {results.count(True)}x"


def test_process_review_credits_bandit_once_and_learns_lessons(app, llm, product):
    row = pipeline.generate_one(app, llm, product, "x")
    taste.record_review(app, row, rating=9, feedback="more dry humor like this")
    out = taste.process_review(app, llm, row["id"], new_rating=True,
                               new_feedback="more dry humor like this")
    assert out["learned"], "learning summary must not be empty"
    # Bandit arms were credited with the human reward.
    arms = db_module.query(app.conn,
                           "SELECT * FROM bandit_arms WHERE product_id = ? AND pulls > 0",
                           (product["id"],))
    assert arms, "rating must move bandit posteriors"
    # A lesson landed in the profile and reaches the prompts.
    lessons = taste.active_lessons(app, product["id"])
    assert lessons
    block = taste.prompt_block(app, product, "x")
    assert "OWNER TASTE PROFILE" in block


def test_lesson_merge_reinforces_and_contradicts(app, llm, product):
    from mark.schemas import AspectSignal, ReviewInterpretation

    row = pipeline.generate_one(app, llm, product, "instagram")
    taste.record_review(app, row, rating=3, feedback="x")
    review = taste.get_review(app, row["id"])
    sig = AspectSignal(aspect="hook", polarity="avoid",
                       directive="Never open with a rhetorical question", severity=0.8)
    interp = ReviewInterpretation(summary="s", signals=[sig])
    first = taste.merge_lessons(app, llm, product["id"], review, interp)
    assert len(first) == 1 and not first[0]["merged"]
    # Identical directive again → support increment, no duplicate row.
    second = taste.merge_lessons(app, llm, product["id"], review, interp)
    assert second[0]["merged"] and second[0]["support"] == 2
    # Opposite polarity, same wording → contradictions; enough of them retires it.
    flip = ReviewInterpretation(summary="s", signals=[
        AspectSignal(aspect="hook", polarity="prefer",
                     directive="Never open with a rhetorical question", severity=0.8)])
    taste.merge_lessons(app, llm, product["id"], review, flip)
    out = taste.merge_lessons(app, llm, product["id"], review, flip)
    assert out[0]["contradictions"] >= 2
    row_db = db_module.query_one(app.conn, "SELECT status FROM taste_lessons WHERE id = ?",
                                 (first[0]["id"],))
    assert row_db["status"] == "retired"


def test_experiment_assignment_and_deterministic_conclusion(app, llm, product):
    exp_id = scientist.create_experiment(app, product["id"], ExperimentProposal(
        aspect="pacing", hypothesis="fast cuts beat slow burns",
        variants=[ExperimentVariant(key="fast", directive="Cut every second."),
                  ExperimentVariant(key="slow", directive="Let it breathe.")],
        rationale="test"))
    assert exp_id
    # Generations get tagged round-robin.
    seen = []
    for _ in range(4):
        row = pipeline.generate_one(app, llm, product, "instagram")
        sctx = db_module.loads(row["strategy_context"], {})
        tag = sctx.get("experiment")
        assert tag and tag["id"] == exp_id
        seen.append(tag["variant"])
        # Rate: "fast" gets 9s, "slow" gets 3s → clear winner.
        taste.record_review(app, row, rating=9 if tag["variant"] == "fast" else 3)
    assert set(seen) == {"fast", "slow"}
    app.settings.learning.experiment_min_samples = 2  # samples are in already
    db_module.execute(app.conn,
                      "UPDATE creative_experiments SET min_samples = 2 WHERE id = ?",
                      (exp_id,))
    concluded = scientist.conclude_ready(app, llm, product)
    assert len(concluded) == 1
    assert concluded[0]["winner"] == "fast"
    # The winning directive became a durable "prefer" lesson.
    lessons = db_module.query(app.conn,
                              "SELECT * FROM taste_lessons WHERE product_id = ? "
                              "AND polarity = 'prefer' AND directive = 'Cut every second.'",
                              (product["id"],))
    assert lessons


def test_scientist_run_writes_notebook(app, llm, product):
    # Give it weak evidence so the offline scientist proposes something.
    for _ in range(3):
        row = pipeline.generate_one(app, llm, product, "x")
        taste.record_review(app, row, rating=3)
        taste.process_review(app, llm, row["id"], new_rating=True)
    out = scientist.run(app, llm, product, force=True)
    assert out is not None and out["notebook_entry"]
    assert scientist.notebook(app, product["id"])


# --------------------------------------------------------------------------- #
# API: the full phone contract through TestClient
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def client(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    for key in ("OPENAI_API_KEY", "FAL_KEY", "UPLOAD_POST_API_KEY", "ELEVENLABS_API_KEY"):
        mp.delenv(key, raising=False)
    mp.setenv("MARK_MOCK", "1")
    home = tmp_path_factory.mktemp("mark-home")
    shutil.copytree(REPO_ROOT / "config", home / "config", dirs_exist_ok=True)
    from tests.conftest import enable_fast_learning

    enable_fast_learning(home)
    app = create_app(home=home, force_mock=True)
    with TestClient(app) as c:
        c.home = home
        yield c
    mp.undo()


def _wait_job(client, job_id: str, timeout: float = 45) -> dict:
    deadline = time.time() + timeout
    job: dict = {}
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.2)
    assert job.get("status") == "done", job
    return job


def _make_campaign_with_video(client, cid: str) -> dict:
    resp = client.post("/api/campaigns", json={
        "id": cid, "name": cid, "description": "d", "target_audience": "t",
        "brand_voice": "v", "platforms": ["tiktok"], "posting_cadence": {"tiktok": 1}})
    assert resp.status_code == 200, resp.text
    job = client.post("/api/generate", json={"campaign_id": cid,
                                             "platforms": ["tiktok"]}).json()
    _wait_job(client, job["job_id"])
    items = client.get(f"/api/content?campaign={cid}").json()
    assert items
    return items[0]


def test_review_feed_and_submit_flow(client):
    item = _make_campaign_with_video(client, "rvtest")
    feed = client.get("/api/review/feed?kind=all&campaign=rvtest").json()
    assert feed, "generated draft with media must appear in the feed"
    entry = next(x for x in feed if x["id"] == item["id"])
    assert entry["campaign"]["name"] == "rvtest"
    assert entry["review"] is None

    # Watch telemetry only — no learn job should spawn.
    out = client.post(f"/api/review/{item['id']}",
                      json={"watch_seconds": 4.2, "video_duration": 12.0}).json()
    assert out["job_id"] is None
    assert out["review"]["watch_seconds"] == 4.2

    # Rating + note + approve in one gesture.
    out = client.post(f"/api/review/{item['id']}",
                      json={"rating": 8, "feedback": "solid, keep this energy",
                            "action": "approve"}).json()
    assert out["status"] == "approved"
    assert out["review"]["rating"] == 8
    assert out["job_id"], "rating+note must trigger the learn job"
    _wait_job(client, out["job_id"])

    # Learning artifacts exist and the dashboard payload carries them.
    insights = client.get("/api/review/insights?campaign=rvtest").json()
    assert insights["totals"]["rated"] == 1
    assert insights["reviews"] and insights["reviews"][0]["rating"] == 8
    assert insights["reviews"][0]["learning"] is not None
    assert insights["trend"]

    # Account profile view.
    acct = client.get("/api/review/account/rvtest").json()
    assert acct["campaign"]["id"] == "rvtest"
    assert acct["stats"]["rated"] == 1
    assert acct["items"]


def test_review_reject_records_rejection_feedback(client):
    item = _make_campaign_with_video(client, "rvreject")
    out = client.post(f"/api/review/{item['id']}",
                      json={"action": "reject", "feedback": "hook is way too slow"}).json()
    assert out["status"] == "rejected"
    if out["job_id"]:
        _wait_job(client, out["job_id"])
    detail = client.get(f"/api/content/{item['id']}").json()
    assert detail["status"] == "rejected"
    assert detail["rejection_feedback"] == "hook is way too slow"


def test_review_rating_validation(client):
    item = _make_campaign_with_video(client, "rvvalid")
    assert client.post(f"/api/review/{item['id']}", json={"rating": 11}).status_code == 422
    assert client.post(f"/api/review/{item['id']}", json={"rating": 0}).status_code == 422
    assert client.post(f"/api/review/{item['id']}",
                       json={"action": "yolo"}).status_code == 400
