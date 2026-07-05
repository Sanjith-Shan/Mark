"""Backend API tests — exercise the real offline (mock) engine through the
FastAPI app with TestClient. No network, no real API keys, everything runs
against a temporary home directory.

Each test creates its own campaign (with an explicit unique id) so tests are
order-independent even though the TestClient/app is module-scoped.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mark.web.server import create_app

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Fixtures / helpers
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
        c.home = home  # expose for tests that need direct DB access
        yield c
    mp.undo()


def wait_job(client: TestClient, job_id: str, timeout: float = 45) -> dict:
    """Poll a job until it finishes; assert it succeeded."""
    deadline = time.time() + timeout
    job: dict = {}
    while time.time() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200, resp.text
        job = resp.json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.2)
    if job.get("status") != "done":
        print("job did not succeed:", job.get("status"), "error:", job.get("error"),
              "message:", job.get("message"))
    assert job.get("status") == "done"
    return job


def make_campaign(client: TestClient, cid: str, platforms: list[str] | None = None) -> str:
    platforms = platforms or ["x"]
    resp = client.post("/api/campaigns", json={
        "id": cid,
        "name": cid.replace("-", " ").title(),
        "description": "A tool that automates boring repetitive work for builders.",
        "target_audience": "indie builders who ship side projects",
        "brand_voice": "casual, punchy, no corporate-speak",
        "platforms": platforms,
        "posting_cadence": {p: 1 for p in platforms},
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == cid
    return cid


def generate_one(client: TestClient, cid: str, platform: str = "x") -> dict:
    """Generate one draft for a campaign and return the content row."""
    resp = client.post("/api/generate",
                       json={"campaign_id": cid, "platforms": [platform], "count": 1})
    assert resp.status_code == 200, resp.text
    wait_job(client, resp.json()["job_id"])
    rows = client.get(f"/api/content?campaign={cid}").json()
    assert rows, "generate produced no content"
    return rows[0]


def approve_and_post(client: TestClient, content_id: int) -> dict:
    """Approve a draft, post it, and return the posted content detail."""
    resp = client.post(f"/api/content/{content_id}/approve")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"
    resp = client.post(f"/api/content/{content_id}/post")
    assert resp.status_code == 200, resp.text
    wait_job(client, resp.json()["job_id"])
    detail = client.get(f"/api/content/{content_id}").json()
    assert detail["status"] == "posted"
    return detail


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_status(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["providers"]) == {"openai", "fal", "upload_post", "elevenlabs"}
    assert all(v == "mock" for v in data["providers"].values())
    assert data["autopilot"]["running"] is False
    assert "counts" in data and "timezone" in data


def test_campaign_crud(client):
    resp = client.post("/api/campaigns", json={
        "name": "TestCo",
        "description": "A tool that automates boring repetitive work.",
        "target_audience": "indie builders",
        "brand_voice": "casual and punchy",
        "platforms": ["x", "linkedin"],
        "posting_cadence": {"x": 1},
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == "testco"
    assert body["platforms"] == ["x", "linkedin"]

    ids = [c["id"] for c in client.get("/api/campaigns").json()]
    assert "testco" in ids

    resp = client.patch("/api/campaigns/testco", json={"active": False})
    assert resp.status_code == 200
    assert resp.json()["active"] == 0

    resp = client.patch("/api/campaigns/testco", json={"active": True})
    assert resp.json()["active"] == 1

    assert client.delete("/api/campaigns/testco").status_code == 200
    ids = [c["id"] for c in client.get("/api/campaigns").json()]
    assert "testco" not in ids


def test_generate_and_studio_flow(client):
    cid = make_campaign(client, "flowco")
    row = generate_one(client, cid)
    assert row["status"] == "draft"
    assert row["caption"]
    assert isinstance(row["hashtags"], list)

    # Edit the draft.
    resp = client.patch(f"/api/content/{row['id']}",
                        json={"caption": "edited caption", "hook": "New hook"})
    assert resp.status_code == 200, resp.text
    edited = resp.json()
    assert edited["caption"] == "edited caption"
    assert edited["hook"] == "New hook"
    assert edited["draft"]["caption"] == "edited caption"
    assert edited["draft"]["hook"] == "New hook"

    # Approve → post → verify post record.
    detail = approve_and_post(client, row["id"])
    assert detail["posts"], "expected at least one post record"
    assert detail["posts"][0]["request_id"]


def test_reject_feedback(client):
    cid = make_campaign(client, "rejectco")
    row = generate_one(client, cid)
    resp = client.post(f"/api/content/{row['id']}/reject",
                       json={"feedback": "too generic"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["rejection_feedback"] == "too generic"


def test_analytics_collect(client):
    cid = make_campaign(client, "statsco")
    row = generate_one(client, cid)
    approve_and_post(client, row["id"])

    resp = client.post(f"/api/analytics/collect?campaign={cid}")
    assert resp.status_code == 200, resp.text
    wait_job(client, resp.json()["job_id"])

    data = client.get(f"/api/analytics?campaign={cid}").json()
    assert data["totals"]["views"] > 0
    assert len(data["table"]) > 0

    resp = client.get(f"/api/comments?campaign={cid}")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
    assert isinstance(body["comments"], list)


def test_trends(client):
    make_campaign(client, "trendco")
    resp = client.post("/api/trends/refresh?campaign=trendco")
    assert resp.status_code == 200, resp.text
    wait_job(client, resp.json()["job_id"])

    trends = client.get("/api/trends").json()
    assert isinstance(trends, list) and trends
    assert "topic" in trends[0] and "trend_score" in trends[0]


def test_insights_learn(client):
    cid = make_campaign(client, "learnco")
    row = generate_one(client, cid)
    approve_and_post(client, row["id"])

    resp = client.post("/api/learn", json={"campaign_id": cid})
    assert resp.status_code == 200, resp.text
    wait_job(client, resp.json()["job_id"])

    data = client.get(f"/api/insights?campaign={cid}").json()
    assert data["campaign"] == cid
    assert isinstance(data["bandit"], list) and data["bandit"]
    assert data["insights"] is not None


def test_settings_roundtrip(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert "llm" in resp.json()["settings"]

    resp = client.patch("/api/settings", json={"settings": {"llm": {"variants": 2}}})
    assert resp.status_code == 200, resp.text
    assert client.get("/api/settings").json()["settings"]["llm"]["variants"] == 2

    resp = client.patch("/api/settings", json={"settings": {"nope": {}}})
    assert resp.status_code == 400


def test_autopilot_endpoints(client):
    resp = client.get("/api/autopilot")
    assert resp.status_code == 200
    data = resp.json()
    assert data["running"] is False
    assert isinstance(data["upcoming"], list)

    try:
        resp = client.post("/api/autopilot/start")
        assert resp.status_code == 200
        assert resp.json()["running"] is True
        assert client.get("/api/autopilot").json()["running"] is True
    finally:
        resp = client.post("/api/autopilot/stop")
        assert resp.status_code == 200
        assert resp.json()["running"] is False


def test_settings_validation_rejects_bad_values(client):
    # Malformed values must be rejected BEFORE they are written to YAML —
    # a persisted bad value would brick every endpoint on the next reload.
    resp = client.patch("/api/settings",
                        json={"settings": {"llm": {"variants": "not-a-number"}}})
    assert resp.status_code == 400
    assert "invalid settings" in resp.json()["detail"]

    # The bad value was never persisted and the API still works.
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["settings"]["llm"].get("variants") != "not-a-number"

    # A valid patch still goes through afterwards.
    resp = client.patch("/api/settings", json={"settings": {"llm": {"variants": 1}}})
    assert resp.status_code == 200, resp.text

    # The learning section is editable (and validated) too.
    resp = client.patch("/api/settings",
                        json={"settings": {"learning": {"holdout_pct": "nope"}}})
    assert resp.status_code == 400
    resp = client.patch("/api/settings",
                        json={"settings": {"learning": {"min_baseline_posts": 1}}})
    assert resp.status_code == 200, resp.text


def test_approve_expired_trend_draft_rejected(client):
    from mark import db as db_module

    cid = make_campaign(client, "expiredco")
    row = generate_one(client, cid)

    # Backdate the trend TTL directly in the DB (no API mutates expires_at).
    conn = db_module.connect(client.home / "data" / "mark.db")
    try:
        db_module.update(conn, "content", row["id"], expires_at="2020-01-01 00:00:00")
    finally:
        conn.close()

    resp = client.post(f"/api/content/{row['id']}/approve")
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"]
    # Status untouched — the draft was not silently approved.
    assert client.get(f"/api/content/{row['id']}").json()["status"] == "draft"


def test_patch_posted_content_rejected(client):
    cid = make_campaign(client, "immutableco")
    row = generate_one(client, cid)
    approve_and_post(client, row["id"])

    resp = client.patch(f"/api/content/{row['id']}", json={"caption": "sneaky edit"})
    assert resp.status_code == 400
    assert "posted" in resp.json()["detail"]
    assert client.get(f"/api/content/{row['id']}").json()["caption"] != "sneaky edit"


def test_content_platform_filter_in_sql(client):
    cid = make_campaign(client, "filterco")
    generate_one(client, cid, platform="x")

    rows = client.get(f"/api/content?campaign={cid}&platform=x&limit=1").json()
    assert len(rows) == 1 and rows[0]["platform"] == "x"
    # Platform filter runs in SQL, so an unmatched platform is empty (not
    # silently hidden by LIMIT applied before the filter).
    assert client.get(f"/api/content?campaign={cid}&platform=linkedin").json() == []


def test_campaign_new_fields_roundtrip(client):
    resp = client.post("/api/campaigns", json={
        "id": "fieldsco",
        "name": "FieldsCo",
        "description": "A lore-driven character universe.",
        "target_audience": "chronically online 18-24s",
        "brand_voice": "absurdist, deadpan",
        "platforms": ["x"],
        "posting_cadence": {"x": 1},
        "kind": "entertainment",
        "content_rating": "edgy",
        "upload_profile": "alt-profile",
        "trend_sources": {"subreddits": ["okbuddyretard", " memes "], "keywords": ["brainrot"]},
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "entertainment"
    assert body["content_rating"] == "edgy"
    assert body["upload_profile"] == "alt-profile"
    assert body["trend_sources"] == {"subreddits": ["okbuddyretard", "memes"],
                                     "keywords": ["brainrot"]}

    # Fields appear in the list response too.
    listed = next(c for c in client.get("/api/campaigns").json() if c["id"] == "fieldsco")
    assert listed["kind"] == "entertainment"

    # Patch updates them; invalid enum values are rejected.
    resp = client.patch("/api/campaigns/fieldsco", json={
        "kind": "product", "content_rating": "clean",
        "trend_sources": {"subreddits": [], "keywords": ["job search"]},
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "product" and body["content_rating"] == "clean"
    assert body["trend_sources"]["keywords"] == ["job search"]

    assert client.patch("/api/campaigns/fieldsco",
                        json={"kind": "cinematic-universe"}).status_code == 400
    assert client.patch("/api/campaigns/fieldsco",
                        json={"content_rating": "nsfw"}).status_code == 400


def test_insights_includes_holdout_lift(client):
    cid = make_campaign(client, "liftco")
    data = client.get(f"/api/insights?campaign={cid}").json()
    assert "holdout_lift" in data  # None until both policy groups have rewarded posts
    assert data["holdout_lift"] is None


def test_experiments_flow(client):
    cid_a = make_campaign(client, "exp-a")
    cid_b = make_campaign(client, "exp-b")
    row_a = generate_one(client, cid_a)
    row_b = generate_one(client, cid_b)
    approve_and_post(client, row_a["id"])
    approve_and_post(client, row_b["id"])
    for cid in (cid_a, cid_b):
        resp = client.post(f"/api/analytics/collect?campaign={cid}")
        assert resp.status_code == 200, resp.text
        wait_job(client, resp.json()["job_id"])

    # Guardrails: unknown campaign / too few variants.
    assert client.post("/api/experiments", json={
        "name": "bad", "campaign_ids": ["exp-a"]}).status_code == 400
    assert client.post("/api/experiments", json={
        "name": "bad", "campaign_ids": ["exp-a", "no-such-campaign"]}).status_code == 404

    resp = client.post("/api/experiments", json={
        "name": "Summer voice test",
        "hypothesis": "variant A's voice out-engages variant B",
        "campaign_ids": [cid_a, cid_b],
    })
    assert resp.status_code == 200, resp.text
    exp = resp.json()
    assert exp["status"] == "running"
    assert exp["campaign_ids"] == [cid_a, cid_b]
    assert exp["metric"] == "engagement_rate"

    listed = client.get("/api/experiments").json()
    assert any(e["id"] == exp["id"] and e["campaign_ids"] == [cid_a, cid_b] for e in listed)

    report = client.get(f"/api/experiments/{exp['id']}/report").json()
    assert [v["campaign_id"] for v in report["variants"]] == [cid_a, cid_b]
    for variant in report["variants"]:
        assert variant["posts"] == 1
        assert variant["views"] > 0
        assert variant["avg_engagement"] >= 0
    assert report["leader"] in (cid_a, cid_b, None)

    resp = client.post(f"/api/experiments/{exp['id']}/conclude",
                       json={"conclusion": "variant A wins"})
    assert resp.status_code == 200, resp.text
    concluded = resp.json()
    assert concluded["status"] == "concluded"
    assert concluded["conclusion"] == "variant A wins"
    assert concluded["ended_at"]

    # Report still works after conclusion; 404s for unknown experiments.
    assert client.get(f"/api/experiments/{exp['id']}/report").status_code == 200
    assert client.get("/api/experiments/999999/report").status_code == 404
    assert client.post("/api/experiments/999999/conclude",
                       json={"conclusion": "x"}).status_code == 404
