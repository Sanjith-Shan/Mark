"""Tests for the paid clipping-campaign discovery template.

Everything runs in forced mock mode (the `app`/`llm` fixtures). A separate,
path-guarded test verifies the flight-data parser against a real saved
ContentRewards /discover HTML capture when present.

Invariant under test: this module is DISCOVERY + TRACKING ONLY. There is no
produce()/join/submit/post path — those are always human web actions.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from mark import db as db_module
from mark.templates import campaigns as C

# Optional real fixture (the 7MB /discover capture used to build the parser).
_REAL_HTML = Path(
    "/private/tmp/claude-501/-Users-sanjithshanmugavel-Documents-Mark/"
    "6d20a087-7bd8-492c-ad4b-e4858f012cb3/scratchpad/cr_discover.html"
)


# --------------------------------------------------------------------------- #
# Fetch / parse
# --------------------------------------------------------------------------- #
def test_fetch_contentrewards_mock_returns_campaigns(app):
    camps = C.fetch_contentrewards(app)
    assert camps, "mock fetch must return deterministic sample campaigns"
    for c in camps:
        assert c["platform"] == "contentrewards"
        assert c["external_id"]
        assert isinstance(c["cpm"], float)
        assert isinstance(c["budget"], float)
        assert isinstance(c["platforms"], list)
    # The gambling sample must be present so the block path is exercisable.
    assert any(c["external_id"] == "sample-roobet-ugc" for c in camps)


def test_money_parser_handles_flight_artifacts():
    assert C._parse_money("$$1,500.00") == 1500.0
    assert C._parse_money("$1.50") == 1.5
    assert C._parse_money(2000) == 2000.0
    assert C._parse_money(None) == 0.0
    assert C._parse_money("garbage") == 0.0


def test_ev_score_ranks_fresh_low_competition_higher():
    targets = {"tiktok", "instagram", "youtube", "x"}
    fresh = {"budget": 10000.0, "budget_used": 300.0, "progress": 3.0, "cpm": 1.5,
             "creators": 41, "platforms": ["tiktok", "instagram"]}
    stale = {"budget": 5000.0, "budget_used": 4600.0, "progress": 92.0, "cpm": 1.0,
             "creators": 380, "platforms": ["tiktok", "instagram"]}
    assert C._ev_score(fresh, targets) > C._ev_score(stale, targets)


def test_cpm_outlier_capped_in_ev():
    targets = {"tiktok"}
    outlier = {"budget": 20000.0, "budget_used": 0.0, "progress": 0.0, "cpm": 1000.0,
               "creators": 0, "platforms": ["tiktok"], "cpm_outlier": True}
    # A $1000 "CPM" (really a flat fee) must not blow up EV — capped at _CPM_EV_CAP.
    ev = C._ev_score(outlier, targets)
    assert ev <= C._CPM_EV_CAP * (20000.0 / 1000.0)


# --------------------------------------------------------------------------- #
# Refresh (upsert) + re-sighting
# --------------------------------------------------------------------------- #
def _count(app) -> int:
    return db_module.query_one(app.conn, "SELECT COUNT(*) AS n FROM clip_campaigns")["n"]


def test_refresh_upserts_and_blocks_gambling(app, llm):
    C.refresh(app, llm)
    rows = db_module.query(app.conn, "SELECT * FROM clip_campaigns")
    assert rows, "refresh must upsert campaigns"
    for r in rows:
        assert r["ev_score"] is not None, "every campaign gets an EV score"
        assert r["platform"] in ("contentrewards", "whop")

    roobet = db_module.query_one(
        app.conn, "SELECT * FROM clip_campaigns WHERE external_id = ?",
        ("sample-roobet-ugc",))
    assert roobet is not None
    assert roobet["blocked"] == 1, "gambling/casino campaign must be brand-safety blocked"

    # A clean campaign must not be blocked, and requirements are extracted.
    clean = db_module.query_one(
        app.conn, "SELECT * FROM clip_campaigns WHERE external_id = ?",
        ("sample-podcast-fresh",))
    assert clean["blocked"] == 0
    reqs = db_module.loads(clean["requirements"], [])
    assert "watermark_required" in reqs and "pinned_comment_required" in reqs


def test_refresh_is_idempotent_no_duplicate_rows(app, llm):
    C.refresh(app, llm)
    n1 = _count(app)
    C.refresh(app, llm)
    n2 = _count(app)
    assert n1 == n2, "re-sighting must update in place, never duplicate"
    # last_seen is populated on every sighting.
    row = db_module.query_one(
        app.conn, "SELECT first_seen, last_seen FROM clip_campaigns LIMIT 1")
    assert row["last_seen"] is not None and row["first_seen"] is not None


def test_refresh_preserves_human_joined_flag(app, llm):
    C.refresh(app, llm)
    db_module.execute(
        app.conn, "UPDATE clip_campaigns SET joined = 1 WHERE external_id = ?",
        ("sample-podcast-fresh",))
    C.refresh(app, llm)  # re-sighting must NOT clobber the human action
    row = db_module.query_one(
        app.conn, "SELECT joined FROM clip_campaigns WHERE external_id = ?",
        ("sample-podcast-fresh",))
    assert row["joined"] == 1


# --------------------------------------------------------------------------- #
# Digest
# --------------------------------------------------------------------------- #
def test_digest_excludes_blocked_and_is_ev_ranked(app, llm):
    C.refresh(app, llm)
    dig = C.digest(app)
    assert dig, "digest returns ranked campaigns"
    assert all(not d["blocked"] for d in dig), "blocked campaigns excluded by default"
    assert not any(d["external_id"] == "sample-roobet-ugc" for d in dig)
    # EV-ranked (descending) among the non-joined set.
    evs = [d["ev_score"] for d in dig]
    assert evs == sorted(evs, reverse=True)
    # Human-action reminder carried on every item.
    assert all("human_only" in d["action"] for d in dig)


def test_digest_include_blocked_surfaces_gambling(app, llm):
    C.refresh(app, llm)
    dig = C.digest(app, include_blocked=True)
    assert any(d["external_id"] == "sample-roobet-ugc" and d["blocked"] for d in dig)


def test_digest_surfaces_joined_and_burn_delta(app, llm):
    C.refresh(app, llm)
    db_module.execute(
        app.conn, "UPDATE clip_campaigns SET joined = 1 WHERE external_id = ?",
        ("sample-podcast-fresh",))
    dig = C.digest(app)
    # Joined campaigns are surfaced first (ORDER BY joined DESC).
    assert dig[0]["joined"] is True
    assert "burn_delta" in dig[0]


# --------------------------------------------------------------------------- #
# The safety invariant: discovery-only, no autonomous submit/post path
# --------------------------------------------------------------------------- #
def test_no_produce_no_autonomous_submit_path():
    # No producer — this is a discovery lane, not a content lane.
    assert not hasattr(C, "produce")
    assert C.STRATEGY.never_auto_approve is True
    assert C.STRATEGY.requires_product is False

    from mark.templates import ensure_loaded, PRODUCERS, DISCOVERY
    ensure_loaded()
    assert "campaign-clips" in DISCOVERY
    assert "campaign-clips" not in PRODUCERS, "discovery lane must not have a producer"

    # No function in the module joins/posts/submits to a platform.
    for name, fn in inspect.getmembers(C, inspect.isfunction):
        assert not any(bad in name.lower() for bad in ("submit", "join_campaign",
                                                       "auto_post", "post_clip")), \
            f"unexpected action function {name!r} — submission/posting must stay human"


# --------------------------------------------------------------------------- #
# Real-HTML parser verification (path-guarded so CI stays green offline)
# --------------------------------------------------------------------------- #
def test_parse_real_discover_html_if_present():
    if not _REAL_HTML.is_file():
        import pytest
        pytest.skip("real /discover fixture not present in this environment")
    html = _REAL_HTML.read_text(encoding="utf-8", errors="replace")
    camps = C._parse_discover(html)
    assert len(camps) > 100, f"expected many real campaigns, got {len(camps)}"
    ids = {c["external_id"] for c in camps}
    assert len(ids) == len(camps), "campaigns must be deduped on id"
    # Real fields must be populated and money parsed sanely.
    sample = next(c for c in camps if c["budget"] > 0)
    assert sample["cpm"] >= 0 and sample["title"]
    # The known $1000 flat-fee outlier is flagged, not treated as a real CPM.
    assert any(c["cpm_outlier"] for c in camps if c["cpm"] > C._CPM_OUTLIER) or \
        all(c["cpm"] <= C._CPM_OUTLIER for c in camps)
