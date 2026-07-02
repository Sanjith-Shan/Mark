"""Bandit and RAG-of-winners tests."""

from mark.learning import bandit


def test_bandit_recommend_shape(app, product):
    picks = bandit.recommend(app, product["id"], "instagram")
    assert set(picks) >= {"hook_style", "content_type", "tone", "post_time"}
    assert picks["content_type"] in app.settings.platform("instagram").content_types


def test_bandit_learns_preference(app, product):
    # Reward 'question' hooks heavily, punish the rest, then check selection skews.
    for _ in range(40):
        bandit.update(app, product["id"], "instagram", "hook_style", "question", 1.0)
        for other in ("story", "statistic", "pain_point"):
            bandit.update(app, product["id"], "instagram", "hook_style", other, 0.0)

    chosen = [bandit.recommend(app, product["id"], "instagram")["hook_style"] for _ in range(50)]
    assert chosen.count("question") >= 35  # strong skew toward the rewarded arm


def test_bandit_update_moves_params(app, product):
    bandit.update(app, product["id"], "x", "tone", "funny", 1.0)
    board = {(a["arm_type"], a["arm_value"]): a for a in bandit.leaderboard(app, product["id"], "x")}
    arm = board[("tone", "funny")]
    assert arm["pulls"] == 1
    assert arm["avg_reward"] == 1.0


def test_winners_retrieve_after_refresh(app, llm, product):
    from mark.analytics import collector
    from mark.learning import winners
    from mark import pipeline

    # Generate, approve, post, collect, then index winners.
    pipeline.generate_all(app, llm, product, ["x"], count=2)
    from mark import store

    for c in store.list_content(app.conn, status="draft", product_id=product["id"]):
        store.set_content_status(app.conn, c["id"], "approved")
    from mark.posting import manager

    manager.post_approved(app, product_id=product["id"])
    collector.collect(app, product_id=product["id"])

    indexed = winners.refresh_winners(app, llm, product)
    assert winners.count(app, product["id"]) >= 1
    results = winners.retrieve(app, llm, "x", "automate boring work", k=2)
    assert all("similarity" in r for r in results)
