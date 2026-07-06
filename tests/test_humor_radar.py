"""Humor radar: sourcing, ranking, the entertainment-only gate, and repost
draft invariants (credit, expiry, never self-approving)."""

from __future__ import annotations

from pathlib import Path

from mark import db as db_module
from mark import humor_radar, store


def _refresh(app, llm):
    return humor_radar.refresh(app, llm)


def test_refresh_stores_scored_finds(app, llm):
    stored = _refresh(app, llm)
    assert stored, "mock sources produced nothing"
    rows = db_module.query(app.conn, "SELECT * FROM humor_finds")
    assert len(rows) >= len(stored)
    for r in rows:
        assert 0.0 <= (r["funny"] or 0) <= 1.0
        assert r["stage"] in ("new", "rising", "mature", "declining")
        assert r["external_id"]


def test_radar_ranks_and_flags_post_now(app, llm):
    _refresh(app, llm)
    finds = humor_radar.radar(app, llm, limit=10)
    assert finds
    scores = [f["radar_score"] for f in finds]
    assert scores == sorted(scores, reverse=True), "radar not ranked"
    # post_now requires postable media + fresh stage + funny enough.
    for f in finds:
        if f["post_now"]:
            assert f["media_url"] and f["stage"] in ("new", "rising")


def test_radar_vetoes_unsafe_and_declining(app, llm):
    _refresh(app, llm)
    db_module.execute(app.conn, "UPDATE humor_finds SET safe = 0 "
                                "WHERE external_id = 'mock-1'")
    db_module.execute(app.conn, "UPDATE humor_finds SET stage = 'declining' "
                                "WHERE external_id = 'mock-2'")
    ids = {f["external_id"] for f in humor_radar.radar(app, llm, limit=20)}
    assert "mock-1" not in ids, "unsafe find survived the veto"
    assert "mock-2" not in ids, "declining find survived the veto"


def test_velocity_across_sightings(app, llm):
    _refresh(app, llm)
    # Backdate the first sightings 3h, then re-sight with a higher score.
    db_module.execute(app.conn,
                      "UPDATE humor_finds SET collected_at = datetime('now', '-3 hours')")
    db_module.execute(app.conn,
                      "UPDATE humor_finds SET raw_score = raw_score - 30 "
                      "WHERE external_id = 'mock-1'")
    _refresh(app, llm)
    row = db_module.query_one(
        app.conn,
        "SELECT velocity, stage FROM humor_finds WHERE external_id = 'mock-1' "
        "ORDER BY collected_at DESC, id DESC LIMIT 1")
    assert row["velocity"] is not None and row["velocity"] > 0
    assert row["stage"] == "rising"


def test_draft_blocked_for_product_campaigns(app, llm, product):
    _refresh(app, llm)
    find = db_module.query_one(app.conn, "SELECT id FROM humor_finds LIMIT 1")
    try:
        humor_radar.draft_repost(app, llm, product, find["id"])
        raise AssertionError("product campaign was allowed to repost a meme")
    except ValueError as exc:
        assert "entertainment" in str(exc)


def test_draft_repost_invariants(app, llm, product):
    store.update_product(app.conn, product["id"], kind="entertainment")
    ent = store.get_product(app.conn, product["id"])
    _refresh(app, llm)
    find = db_module.query_one(
        app.conn, "SELECT id FROM humor_finds WHERE media_url IS NOT NULL "
                  "OR source = 'reddit' LIMIT 1")
    row = humor_radar.draft_repost(app, llm, ent, find["id"], platform="x")

    # Never self-approves — a human judges every repost.
    assert row["status"] == "draft"
    # Credit + provenance carried.
    assert "🎥" in (row["caption"] or "")
    sctx = db_module.loads(row["strategy_context"], {})
    assert sctx["strategy"] == humor_radar.STRATEGY_ID
    assert sctx["external_id"]
    # Expires with the meme window.
    assert row["expires_at"] is not None
    # Media landed on disk (mock placeholder offline).
    paths = db_module.loads(row["media_paths"], [])
    assert paths and Path(paths[0]).exists()


def test_auto_draft_respects_gates(app, llm, product):
    store.update_product(app.conn, product["id"], kind="entertainment")
    ent = store.get_product(app.conn, product["id"])
    _refresh(app, llm)
    app.settings.humor_radar.auto_draft = True
    app.settings.humor_radar.min_funny = 0.0
    drafted = humor_radar.auto_draft(app, llm, ent)
    assert len(drafted) <= app.settings.humor_radar.max_drafts_per_day
    # Re-running never duplicates the same finds.
    again = humor_radar.auto_draft(app, llm, ent)
    ids_a = {db_module.loads(d["strategy_context"], {})["external_id"] for d in drafted}
    ids_b = {db_module.loads(d["strategy_context"], {})["external_id"] for d in again}
    assert not (ids_a & ids_b)
    # Product campaigns never auto-draft.
    store.update_product(app.conn, product["id"], kind="product")
    prod = store.get_product(app.conn, product["id"])
    assert humor_radar.auto_draft(app, llm, prod) == []
