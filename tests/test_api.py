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
    app = create_app(home=home, force_mock=True)
    with TestClient(app) as c:
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
