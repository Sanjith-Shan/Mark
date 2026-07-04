"""Tests for the strategy framework, humor engine, characters, and trend
fast-path — all offline/mock mode."""

from __future__ import annotations

from mark import characters, db as db_module, humor, store, strategies
from mark.schemas import ContentDraft, ContentPlan


# --------------------------------------------------------------------------- #
# Strategy framework
# --------------------------------------------------------------------------- #
def test_catalog_is_wired():
    assert len(strategies.STRATEGIES) >= 10
    ids = [s.id for s in strategies.STRATEGIES]
    assert len(ids) == len(set(ids)), "duplicate strategy ids"
    for s in strategies.STRATEGIES:
        assert s.platforms, f"{s.id} has no platform fit"
        assert s.content_types, f"{s.id} has no content types"
        assert s.humor_level in ("none", "light", "full")


def test_eligibility_respects_platform_and_types(app, product):
    # x allows image/text/thread/video → fake-text-drama (video/carousel) applies
    # only where those types are allowed.
    for s in strategies.eligible(app, product, "x"):
        assert s.fits("x")
        allowed = set(app.settings.platform("x").content_types)
        assert any(t in allowed for t in s.content_types)
    # Bluesky is text-only in config → video-only strategies must not qualify.
    bs = strategies.eligible(app, product, "bluesky")
    assert all("text" in s.content_types for s in bs)


def test_product_allowlist_gates_pick(app, product):
    store.update_product(app.conn, product["id"], strategies=["pain-point-povs"])
    fresh = store.get_product(app.conn, product["id"])
    pool = strategies.eligible(app, fresh, "x")
    assert [s.id for s in pool] == ["pain-point-povs"]
    picked = strategies.pick(app, fresh, "x")
    assert picked.id == "pain-point-povs"


def test_bandit_choice_wins_when_eligible(app, product):
    picked = strategies.pick(app, product, "x", bandit_choice="contrarian-takes")
    assert picked.id == "contrarian-takes"
    # Ineligible bandit choice falls back to weighted sampling.
    picked = strategies.pick(app, product, "x", bandit_choice="not-a-strategy")
    assert picked is not None


def test_strategy_is_a_bandit_arm(app, product):
    from mark.learning import bandit

    values = bandit.candidate_values(app, "x")
    assert "strategy" in values and "contrarian-takes" in values["strategy"]
    assert "humor_mechanism" in values and "emotional_target" in values
    picks = bandit.recommend(app, product["id"], "x")
    assert picks["strategy"] in values["strategy"]


def test_generation_records_strategy_and_emotion(app, llm, product):
    from mark import pipeline

    row = pipeline.generate_one(app, llm, product, "x")
    sctx = db_module.loads(row["strategy_context"], {})
    assert sctx.get("strategy") in [s.id for s in strategies.STRATEGIES]
    assert sctx.get("emotional_target")


def test_never_auto_approve_strategy(app, llm, product):
    from mark import pipeline

    # Force auto-approve on, restrict to the draft-only strategy.
    app.settings.approval.auto_approve = True
    store.update_product(app.conn, product["id"], strategies=["founder-build-log"])
    fresh = store.get_product(app.conn, product["id"])
    row = pipeline.generate_one(app, llm, fresh, "x")
    assert row["status"] == "draft"  # founder voice is never auto-approved


# --------------------------------------------------------------------------- #
# Humor engine
# --------------------------------------------------------------------------- #
def _plan(**kw):
    base = dict(platform="x", content_type="text", topic="rejection emails",
                angle="the 2am timestamp", hook_style="pain_point", tone="funny")
    base.update(kw)
    return ContentPlan(**base)


def _draft():
    return ContentDraft(caption="Rejections arrive at odd hours.\nIt stings.",
                        hook="Rejections arrive at odd hours.")


def test_punch_up_offline_applies_candidate(app, llm, product):
    draft = humor.punch_up(app, llm, product, "x", _plan(), _draft(), level="full")
    assert draft.humor_mechanism in [m for m in __import__("mark.constants", fromlist=["HUMOR_MECHANISMS"]).HUMOR_MECHANISMS]
    assert draft.humor_persona
    assert draft.caption


def test_punch_up_disabled_returns_original(app, llm, product):
    app.settings.humor.enabled = False
    original = _draft()
    out = humor.punch_up(app, llm, product, "x", _plan(), original, level="full")
    assert out is original
    assert out.humor_mechanism is None


def test_scaffold_incomplete_candidates_are_rejected():
    from mark.schemas import JokeCandidate

    ok = JokeCandidate(persona="cynic", mechanism="setup_subversion", hook="h",
                       caption="c", target_assumption="a", connector="b",
                       reinterpretation="r", punch_word="p")
    missing = JokeCandidate(persona="cynic", mechanism="setup_subversion",
                            hook="h", caption="c")
    assert humor._scaffold_complete(ok)
    assert not humor._scaffold_complete(missing)


def test_punch_beat_inserted_for_video_scripts():
    s = humor._ensure_punch_beat("line one\nline two\nthe punch")
    assert s.endswith("\n\nthe punch")


def test_writer_triggers_humor_for_funny_tone(app, llm, product):
    from mark.agents import writer

    plan = _plan(tone="funny", content_type="text")
    draft = writer.write_content(app, llm, product, "x", plan)
    # Offline mock pipeline still runs the full humor path and tags the draft.
    assert draft.humor_mechanism is not None


# --------------------------------------------------------------------------- #
# Characters
# --------------------------------------------------------------------------- #
def test_character_crud_and_reference_sheet(app, llm, product):
    c = characters.create(
        app, product["id"], name="Blobby",
        persona="a tired blob that applies to jobs", visual_desc="a pastel blob",
        catchphrases=["we circle back."])
    assert c["catchphrases"] == ["we circle back."]
    assert characters.active_character(app, product["id"])["id"] == c["id"]

    path = characters.ensure_reference_image(app, llm, c)
    assert path.exists()
    again = characters.ensure_reference_image(app, llm, characters.get(app, c["id"]))
    assert again == path  # idempotent


def test_character_sync_from_config(app):
    # The repo config ships Poli/TalentBot for product "sudoapply"; add the product
    # so the FK is satisfied, then sync.
    from mark.config import ProductConfig

    store.upsert_product(app.conn, ProductConfig(
        id="sudoapply", name="SudoApply", description="d", target_audience="t",
        brand_voice="v"), active=False)
    synced = characters.sync_from_config(app)
    names = {c["name"] for c in synced}
    assert "Poli" in names
    poli = next(c for c in synced if c["name"] == "Poli")
    assert "APPLICANT #4,217" in poli["visual_desc"]
    assert poli["lore_state"].get("applications_submitted") == 4217
    # Re-sync keeps lore (update path, not duplicate insert).
    characters.on_episode_approved(app, poli["id"])
    resynced = characters.sync_from_config(app)
    poli2 = next(c for c in resynced if c["name"] == "Poli")
    assert poli2["id"] == poli["id"]
    assert poli2["lore_state"]["episodes_posted"] == 1
    assert poli2["lore_state"]["applications_submitted"] > 4217


def test_mascot_content_carries_character(app, llm, product):
    from mark import pipeline

    characters.create(app, product["id"], name="Blobby",
                      persona="tired blob", visual_desc="a pastel blob")
    store.update_product(app.conn, product["id"], strategies=["unhinged-mascot"])
    fresh = store.get_product(app.conn, product["id"])
    row = pipeline.generate_one(app, llm, fresh, "x")
    sctx = db_module.loads(row["strategy_context"], {})
    assert sctx["strategy"] == "unhinged-mascot"
    assert sctx["character"] == "Blobby"
    assert sctx["character_id"]


# --------------------------------------------------------------------------- #
# Trend fast-path
# --------------------------------------------------------------------------- #
def test_trend_stages_and_hot_veto(app, llm, product):
    from mark.trends import aggregator

    # First sighting, modest score → "new"; big first sighting → "mature".
    assert aggregator._stage(None, 0.3) == "new"
    assert aggregator._stage(None, 0.9) == "mature"
    assert aggregator._stage(0.05, 0.5) == "rising"
    assert aggregator._stage(-0.05, 0.5) == "declining"

    db_module.insert(app.conn, "trends", source="reddit", topic="fresh pain",
                     trend_score=0.8, stage="new", metadata={"safe": True})
    db_module.insert(app.conn, "trends", source="reddit", topic="dying meme",
                     trend_score=0.9, stage="declining", metadata={"safe": True})
    db_module.insert(app.conn, "trends", source="reddit", topic="cursed origin",
                     trend_score=0.9, stage="new", metadata={"safe": False})
    db_module.insert(app.conn, "trends", source="tiktok", topic="sound meme",
                     trend_score=0.9, stage="new",
                     metadata={"safe": True, "sound_dependent": True})
    hot = aggregator.hot_trends(app)
    topics = [t["topic"] for t in hot]
    assert "fresh pain" in topics
    assert "dying meme" not in topics       # declining = hard veto
    assert "cursed origin" not in topics    # unsafe = hard veto
    assert "sound meme" not in topics       # sound-dependent excluded from auto
    manual = aggregator.hot_trends(app, for_auto_react=False)
    assert "sound meme" in [t["topic"] for t in manual]


def test_react_generates_expiring_content(app, llm, product):
    from mark.trends import aggregator

    trend = {"topic": "the 2:47am rejection email", "stage": "new",
             "trend_score": 0.9, "style_notes": "screenshot + dry caption"}
    rows = aggregator.react(app, llm, product, trend=trend, platforms=["x"])
    assert len(rows) == 1
    row = store.get_content(app.conn, rows[0]["id"])
    assert row["expires_at"] is not None
    sctx = db_module.loads(row["strategy_context"], {})
    assert sctx["forced_trend"] == "the 2:47am rejection email"

    # Daily cap enforced via activity log.
    app.settings.trends.max_reactions_per_day = 1
    again = aggregator.react(app, llm, product, trend=trend, platforms=["x"])
    assert again == []


def test_expire_stale_content(app, llm, product):
    from mark.trends import aggregator

    cid = store.insert_content(
        app.conn, product_id=product["id"], platform="x", content_type="text",
        caption="old trend post", hashtags=[], hook="h", media_paths=[],
        media_urls=[], strategy_context={}, status="draft")
    db_module.execute(app.conn,
                      "UPDATE content SET expires_at = datetime('now', '-1 hour') "
                      "WHERE id = ?", (cid,))
    n = aggregator.expire_stale_content(app)
    assert n == 1
    assert store.get_content(app.conn, cid)["status"] == "rejected"


def test_refresh_fast_stores_velocity_and_stage(app, llm, product):
    from mark.trends import aggregator

    out = aggregator.refresh_fast(app, llm, product)
    assert out, "fast refresh returned nothing (fallback sources should fire)"
    assert all("stage" in t for t in out)
    row = db_module.query_one(app.conn, "SELECT stage FROM trends LIMIT 1")
    assert row is not None


# --------------------------------------------------------------------------- #
# Judge calibration + cascade ladder
# --------------------------------------------------------------------------- #
def _seed_posted(app, product, platform, hook, rate, days_ago=3):
    cid = store.insert_content(
        app.conn, product_id=product["id"], platform=platform, content_type="text",
        caption=f"{hook} body", hashtags=[], hook=hook, media_paths=[],
        media_urls=[], strategy_context={"strategy": "pain-point-povs"},
        status="posted")
    pid = db_module.insert(app.conn, "posts", content_id=cid, platform=platform,
                           platform_post_id=f"pp{cid}", request_id=f"mock-{cid}")
    db_module.execute(app.conn,
                      "UPDATE posts SET posted_at = datetime('now', ?) WHERE id = ?",
                      (f"-{days_ago} days", pid))
    db_module.insert(app.conn, "metrics", post_id=pid, views=1000,
                     likes=int(rate * 1000), engagement_rate=rate)
    return cid


def test_calibration_pairs_from_engagement(app, product):
    from mark.learning import calibration

    _seed_posted(app, product, "x", "the winner hook", 0.20)
    _seed_posted(app, product, "x", "the loser hook", 0.02)
    pairs = calibration.preference_pairs(app, product["id"], "x")
    assert len(pairs) == 1
    assert pairs[0]["winner"]["hook"] == "the winner hook"
    block = calibration.calibration_block(app, product["id"], "x")
    assert "the winner hook" in block and "the loser hook" in block
    # Close engagement = noise, not preference.
    assert calibration.preference_pairs(app, product["id"], "instagram") == []


def test_cascade_adapts_winner_cross_platform(app, llm, product):
    from mark import pipeline

    src = _seed_posted(app, product, "x", "a winning x post", 0.25)
    row = pipeline.adapt_content(app, llm, src, "threads")
    assert row["platform"] == "threads"
    assert row["status"] in ("draft", "approved")
    sctx = db_module.loads(row["strategy_context"], {})
    assert sctx["cascaded_from"] == src
    assert sctx["cascade_source_platform"] == "x"


def test_reply_drafting_and_sensitive_gate(app, llm, product):
    from mark import replies

    cid = _seed_posted(app, product, "x", "a post with comments", 0.1)
    post = db_module.query_one(app.conn, "SELECT id FROM posts WHERE content_id = ?",
                               (cid,))
    db_module.insert(app.conn, "comments", post_id=post["id"],
                     comment_text="is this free?", author="user1", platform="x")
    db_module.insert(app.conn, "comments", post_id=post["id"],
                     comment_text="i can't afford rent and my visa expires soon",
                     author="user2", platform="x")

    drafted = replies.draft_replies(app, llm, product)
    assert len(drafted) == 2
    by_author = {d["author"]: d for d in drafted}
    assert by_author["user1"]["reply_text"]
    assert by_author["user1"]["sensitive"] == 0
    assert by_author["user2"]["sensitive"] == 1  # human-only

    # Idempotent: already-drafted comments aren't re-drafted.
    assert replies.draft_replies(app, llm, product) == []

    # Status transitions.
    rid = by_author["user1"]["id"]
    out = replies.set_status(app, rid, "posted", reply_text="edited reply")
    assert out["status"] == "posted" and out["reply_text"] == "edited reply"


def test_job_cascade_skips_duplicates(app, llm, product):
    from mark.scheduler import engine

    # One clear winner vs a weak baseline post on x → cascades to threads once.
    _seed_posted(app, product, "x", "weak post", 0.01)
    _seed_posted(app, product, "x", "monster winner", 0.30)
    app.settings.platforms["threads"] = app.settings.platform("threads")
    app.settings.platforms["threads"].enabled = True
    engine.job_cascade(app, llm)
    n1 = db_module.query_one(
        app.conn, "SELECT COUNT(*) AS n FROM content WHERE platform = 'threads' "
        "AND strategy_context LIKE '%cascaded_from%'")["n"]
    assert n1 >= 1
    engine.job_cascade(app, llm)  # idempotent — no duplicate adaptations
    n2 = db_module.query_one(
        app.conn, "SELECT COUNT(*) AS n FROM content WHERE platform = 'threads' "
        "AND strategy_context LIKE '%cascaded_from%'")["n"]
    assert n2 == n1
