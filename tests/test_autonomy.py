"""Graduated autonomy, self-monitoring, content ratings, entertainment mode."""

from __future__ import annotations

from mark import autonomy, monitor, rating, store, strategies
from mark import db as db_module


# --------------------------------------------------------------------------- #
# Ratings
# --------------------------------------------------------------------------- #
def test_effective_rating_platform_caps():
    edgy = {"content_rating": "edgy"}
    assert rating.effective_rating(edgy, "tiktok") == "edgy"
    assert rating.effective_rating(edgy, "linkedin") == "clean"   # platform ceiling
    assert rating.effective_rating(edgy, "bluesky") == "standard"
    clean = {"content_rating": "clean"}
    assert rating.effective_rating(clean, "tiktok") == "clean"    # campaign choice wins
    assert rating.effective_rating({}, "x") == "standard"          # default


def test_min_benignness_moves_with_rating():
    base = 0.5
    assert rating.min_benignness(base, {"content_rating": "edgy"}, "tiktok") < base
    assert rating.min_benignness(base, {"content_rating": "clean"}, "tiktok") > base
    # Floor holds even at edgy.
    assert rating.min_benignness(0.2, {"content_rating": "edgy"}, "x") >= rating.BENIGNNESS_FLOOR


# --------------------------------------------------------------------------- #
# Entertainment mode
# --------------------------------------------------------------------------- #
def test_entertainment_excludes_product_strategies(app, product):
    store.update_product(app.conn, product["id"], kind="entertainment")
    ent = store.get_product(app.conn, product["id"])
    ids = {s.id for s in strategies.eligible(app, ent, "x")}
    assert "demo-magic" not in ids
    assert "social-proof-receipts" not in ids
    assert "founder-build-log" not in ids
    assert "pain-point-povs" in ids  # non-product strategies survive
    # The bandit arm space honors the same restriction.
    assert "demo-magic" not in strategies.candidate_ids(app, "x", product=ent)


def test_strategy_catalog_overrides(app, product):
    store.update_product(app.conn, product["id"], strategy_catalog={
        "pain-point-povs": {"strategist_brief": "CUSTOM DOMAIN BRIEF"}})
    prod = store.get_product(app.conn, product["id"])
    cat = {s.id: s for s in strategies.catalog_for(prod)}
    assert cat["pain-point-povs"].strategist_brief == "CUSTOM DOMAIN BRIEF"
    # Base catalog untouched.
    assert strategies.get("pain-point-povs").strategist_brief != "CUSTOM DOMAIN BRIEF"


# --------------------------------------------------------------------------- #
# Graduated autonomy
# --------------------------------------------------------------------------- #
def _make_draft_row(app, product, platform="x"):
    return store.insert_content(
        app.conn, product_id=product["id"], platform=platform, content_type="text",
        caption="c", hook="h", status="draft", strategy_context={})


def test_graduated_requires_track_record(app, product):
    app.settings.approval.mode = "graduated"
    cid = _make_draft_row(app, product)
    strategy = strategies.get("pain-point-povs")
    qa = {"hook_strength": 9, "brand_fit": 9, "scroll_stopping": 9}
    # High QA but zero track record → stays draft.
    assert not autonomy.maybe_auto_approve(app, product, cid, "x", "text",
                                           strategy=strategy, qa=qa)
    assert store.get_content(app.conn, cid)["status"] == "draft"

    # Build the track record on the strategy arm, then it approves.
    from mark.learning import bandit

    for _ in range(6):
        bandit.update(app, product["id"], "x", "strategy", "pain-point-povs", 0.7)
    cid2 = _make_draft_row(app, product)
    assert autonomy.maybe_auto_approve(app, product, cid2, "x", "text",
                                       strategy=strategy, qa=qa)
    assert store.get_content(app.conn, cid2)["status"] == "approved"


def test_graduated_requires_qa(app, product):
    app.settings.approval.mode = "graduated"
    from mark.learning import bandit

    for _ in range(6):
        bandit.update(app, product["id"], "x", "strategy", "pain-point-povs", 0.7)
    strategy = strategies.get("pain-point-povs")
    cid = _make_draft_row(app, product)
    # Track record fine, but weak QA scores → stays draft.
    weak = {"hook_strength": 4, "brand_fit": 5, "scroll_stopping": 4}
    assert not autonomy.maybe_auto_approve(app, product, cid, "x", "text",
                                           strategy=strategy, qa=weak)


def test_never_auto_approve_strategy(app, product):
    app.settings.approval.mode = "full"
    strategy = strategies.get("founder-build-log")
    cid = _make_draft_row(app, product)
    assert not autonomy.maybe_auto_approve(app, product, cid, "x", "text",
                                           strategy=strategy, qa={})


# --------------------------------------------------------------------------- #
# Self-monitoring
# --------------------------------------------------------------------------- #
def test_collapse_detection_pauses_platform(app, product):
    # Five rewarded posts far below baseline → pause + no self-approval.
    for i in range(5):
        cid = _make_draft_row(app, product)
        pid = store.insert_post(app.conn, content_id=cid, platform="x",
                                platform_post_id=f"p{i}", request_id=f"r{i}")
        db_module.update(app.conn, "posts", pid, reward=0.1,
                         rewarded_at="2026-07-01 00:00:00")
        store.set_content_status(app.conn, cid, "posted")
    collapses = monitor.check_engagement_collapse(app, product)
    assert collapses and collapses[0]["platform"] == "x"
    assert monitor.is_paused(app, product["id"], "x")
    # A paused platform never self-approves, even in full mode.
    app.settings.approval.mode = "full"
    cid = _make_draft_row(app, product)
    assert not autonomy.maybe_auto_approve(app, product, cid, "x", "text", qa={})
    # Manual resume clears it.
    monitor.resume(app, product["id"], "x")
    assert not monitor.is_paused(app, product["id"], "x")


def test_spend_freeze(app):
    app.settings.safety.max_daily_spend_usd = 1.0
    db_module.insert(app.conn, "costs", provider="openai", operation="chat",
                     model="gpt-5.4-mini", usd=2.5, mocked=0)
    assert monitor.check_spend(app) is not None
    assert monitor.generation_frozen(app)


# --------------------------------------------------------------------------- #
# UTM tracking
# --------------------------------------------------------------------------- #
def test_tracked_url():
    from mark.posting.manager import tracked_url

    url = tracked_url("https://testco.example/landing?ref=1", "x", "testco", 42)
    assert "utm_source=x" in url and "utm_campaign=testco" in url \
        and "utm_content=42" in url and "ref=1" in url
    # Non-URLs pass through untouched.
    assert tracked_url("not a url", "x", "t", 1) == "not a url"
