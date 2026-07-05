"""Tests for first-class series bookkeeping (src/mark/series.py): ensure/record,
episode numbering from the series table, stats refresh, and THE KILL RULE."""

from __future__ import annotations

from mark import characters, db as db_module, series, store, strategies

STRATEGY_ID = "satirical-ui-franchise"  # episodic (series_format), no character


def _strategy():
    return strategies.get(STRATEGY_ID)


def _seed_episode(app, product, reward, days_ago):
    """A posted + rewarded episode of the strategy's series."""
    cid = store.insert_content(
        app.conn, product_id=product["id"], platform="x", content_type="image",
        caption="episode", hashtags=[], hook="h", media_paths=[], media_urls=[],
        strategy_context={"strategy": STRATEGY_ID}, status="posted")
    pid = db_module.insert(app.conn, "posts", content_id=cid, platform="x",
                           platform_post_id=f"pp{cid}", request_id=f"mock-{cid}")
    db_module.execute(
        app.conn,
        "UPDATE posts SET posted_at = datetime('now', ?), "
        "rewarded_at = datetime('now'), reward = ? WHERE id = ?",
        (f"-{days_ago} days", reward, pid))
    return cid


def test_ensure_series_is_get_or_create(app, product):
    s1 = series.ensure_series(app, product, _strategy(), "x")
    assert s1["status"] == "active"
    assert s1["episodes"] == 0
    assert s1["premise"]  # first sentence of the series recipe
    s2 = series.ensure_series(app, product, _strategy(), "instagram")
    assert s2["id"] == s1["id"], "one series per (product, strategy) — cross-platform"


def test_record_episode_increments(app, product):
    s = series.ensure_series(app, product, _strategy(), "x")
    series.record_episode(app, s["id"])
    s = series.record_episode(app, s["id"])
    assert s["episodes"] == 2


def test_on_content_generated_tracks_only_episodic(app, product):
    s = series.on_content_generated(app, product, _strategy(), "x")
    assert s is not None and s["episodes"] == 1
    # Non-episodic strategy → no series.
    assert series.on_content_generated(
        app, product, strategies.get("contrarian-takes"), "x") is None


def test_episode_number_reads_from_series(app, product):
    strat = _strategy()
    # Without a series row: count-based fallback (no kept content yet → 1).
    assert strategies.episode_number(app, product, "x", strat) == 1
    s = series.ensure_series(app, product, strat, "x")
    series.record_episode(app, s["id"])
    series.record_episode(app, s["id"])
    assert strategies.episode_number(app, product, "x", strat) == 3


def test_episode_number_fallback_counts_content(app, product):
    # No series row, but one kept content row under the strategy → episode 2.
    store.insert_content(
        app.conn, product_id=product["id"], platform="x", content_type="image",
        caption="c", hashtags=[], hook="h", media_paths=[], media_urls=[],
        strategy_context={"strategy": STRATEGY_ID}, status="posted")
    assert strategies.episode_number(app, product, "x", _strategy()) == 2


def test_update_stats_stores_trailing_rewards(app, product):
    s = series.ensure_series(app, product, _strategy(), "x")
    _seed_episode(app, product, 0.7, days_ago=3)
    _seed_episode(app, product, 0.5, days_ago=2)
    series.record_episode(app, s["id"])
    series.record_episode(app, s["id"])
    updated = series.update_stats(app, product["id"])
    s = next(u for u in updated if u["id"] == s["id"])
    assert s["last_engagement"] == [0.7, 0.5]
    assert abs(s["avg_engagement"] - 0.6) < 1e-6
    assert s["status"] == "active"  # healthy series untouched


def test_kill_rule_retires_and_spawns_replacement(app, llm, product):
    s = series.ensure_series(app, product, _strategy(), "x")
    old_premise = s["premise"]
    for i, reward in enumerate((0.2, 0.3, 0.1)):
        _seed_episode(app, product, reward, days_ago=3 - i)
        series.record_episode(app, s["id"])

    result = series.run_maintenance(app, llm, product)

    # Retired with a reason explaining the numbers.
    dead = series.get_series(app, s["id"])
    assert dead["status"] == "retired"
    assert "0.4" in dead["retired_reason"]
    assert [r["id"] for r in result["retired"]] == [s["id"]]

    # Error-level activity alert logged.
    alerts = db_module.query(
        app.conn,
        "SELECT * FROM activity WHERE kind = 'series' AND level = 'error'")
    assert len(alerts) == 1

    # A replacement series exists: same strategy, fresh premise, active, ep 0.
    replacement = series.active_series(app, product["id"], STRATEGY_ID)
    assert replacement is not None
    assert replacement["id"] != s["id"]
    assert replacement["episodes"] == 0
    assert replacement["premise"] != old_premise
    assert [r["id"] for r in result["spawned"]] == [replacement["id"]]

    # Episode numbering restarts on the replacement.
    assert strategies.episode_number(app, product, "x", _strategy()) == 1


def test_kill_rule_needs_three_consecutive_low_episodes(app, llm, product):
    s = series.ensure_series(app, product, _strategy(), "x")
    for i, reward in enumerate((0.2, 0.9, 0.1)):  # a hit breaks the streak
        _seed_episode(app, product, reward, days_ago=3 - i)
        series.record_episode(app, s["id"])
    series.run_maintenance(app, llm, product)
    assert series.get_series(app, s["id"])["status"] == "active"


def test_character_series_premise_uses_persona(app, product):
    characters.create(app, product["id"], name="Blobby",
                      persona="Blobby cannot stop applying to jobs. It is tired.",
                      visual_desc="a pastel blob")
    strat = strategies.get("unhinged-mascot")
    s = series.ensure_series(app, product, strat, "x")
    assert "Blobby cannot stop applying to jobs." in s["premise"]
