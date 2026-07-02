"""Seed a demo home directory with two campaigns and a lived-in history.

Runs the REAL offline engine end-to-end (generation → approval → posting →
metrics → trends → learning), so screenshots and manual testing show the app
exactly as it behaves in production — just with mock providers.

Usage: python3 scripts/demo_seed.py <home_dir>
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

os.environ["MARK_MOCK"] = "1"
for key in ("OPENAI_API_KEY", "FAL_KEY", "UPLOAD_POST_API_KEY", "ELEVENLABS_API_KEY"):
    os.environ.pop(key, None)


def main(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    if (home / "config").exists():
        shutil.rmtree(home / "config")
    shutil.copytree(REPO / "config", home / "config")

    from mark.app import get_app
    from mark.config import ProductConfig
    from mark.llm import LLM
    from mark import pipeline, store
    from mark.analytics import collector, sentiment
    from mark.learning import feedback
    from mark.posting import manager
    from mark.trends import aggregator

    app = get_app(home=home, force_mock=True)
    llm = LLM(app)

    campaigns = [
        ProductConfig(
            id="sudoapply", name="SudoApply",
            description="AI-powered job application platform: multi-resume support, "
                        "ATS autofill Chrome extension, Kanban application tracker. "
                        "Built for students hunting internships.",
            target_audience="College students (18-24) grinding through internship "
                            "applications; tech-savvy, live on TikTok/LinkedIn.",
            brand_voice="Casual, relatable, slightly irreverent. Fellow-student energy, "
                        "memes welcome, zero corporate speak.",
            website_url="https://sudoapply.com",
            platforms=["tiktok", "instagram", "x", "linkedin"],
            posting_cadence={"tiktok": 2, "instagram": 2, "x": 3, "linkedin": 1},
        ),
        ProductConfig(
            id="notewise", name="NoteWise",
            description="AI lecture-notes app that turns recordings into structured, "
                        "searchable study guides with flashcards and spaced repetition.",
            target_audience="University students who record lectures and cram before "
                            "exams; heavy Instagram and YouTube users.",
            brand_voice="Encouraging, sharp, a little nerdy. Study-buddy energy — "
                        "practical tips over hype.",
            website_url="https://notewise.app",
            platforms=["instagram", "x", "bluesky", "threads"],
            posting_cadence={"instagram": 2, "x": 2, "bluesky": 1, "threads": 1},
        ),
    ]
    for cfg in campaigns:
        store.upsert_product(app.conn, cfg, active=False)
        store.update_product(app.conn, cfg.id, active=1)
        print(f"campaign: {cfg.id}")

    # Trends first so generation has context.
    for cfg in campaigns:
        aggregator.refresh(app, llm, store.get_product(app.conn, cfg.id))
    print("trends refreshed")

    # Generate a queue: some drafts stay drafts, some get approved, some posted.
    plan = [
        ("sudoapply", ["x", "linkedin", "instagram"]),   # skip video platforms: fast
        ("notewise", ["x", "instagram", "threads", "bluesky"]),
    ]
    posted, drafts = 0, 0
    for pid, platforms in plan:
        product = store.get_product(app.conn, pid)
        for i, platform in enumerate(platforms * 2):
            row = pipeline.generate_one(app, llm, product, platform)
            if i % 3 == 2:
                drafts += 1
                continue  # leave as draft
            store.set_content_status(app.conn, row["id"], "approved")
            manager.post_content(app, store.get_content(app.conn, row["id"]))
            posted += 1
    print(f"content: {posted} posted, {drafts} drafts")

    # A rejected one with feedback (feeds the learning loop).
    product = store.get_product(app.conn, "sudoapply")
    row = pipeline.generate_one(app, llm, product, "x")
    store.set_content_status(app.conn, row["id"], "rejected",
                             rejection_feedback="too generic — needs a concrete student story")

    # Backdate posts across the past ~10 days so charts show a real time series.
    rows = app.conn.execute("SELECT id FROM posts ORDER BY id").fetchall()
    for i, row in enumerate(rows):
        days_ago = (len(rows) - 1 - i) % 10
        app.conn.execute(
            "UPDATE posts SET posted_at = datetime('now', ?) WHERE id = ?",
            (f"-{days_ago} days", row["id"]))
        app.conn.execute(
            "UPDATE content SET posted_at = datetime('now', ?), created_at = datetime('now', ?) "
            "WHERE id = (SELECT content_id FROM posts WHERE id = ?)",
            (f"-{days_ago} days", f"-{days_ago} days", row["id"]))
    app.conn.commit()

    # Metrics over "time": collect several rounds so charts have shape, and
    # backdate each snapshot near its post date.
    for round_ in range(4):
        collector.collect(app)
        app.conn.execute(
            "UPDATE metrics SET collected_at = ("
            "  SELECT datetime(p.posted_at, '+' || (? * 6) || ' hours')"
            "  FROM posts p WHERE p.id = metrics.post_id)"
            "WHERE collected_at >= datetime('now', '-1 minute')", (round_,))
        app.conn.commit()
    sentiment.analyze_unscored(app, llm)
    print("metrics + sentiment collected")

    # Learning loop → winners, bandit updates, insights.
    for cfg in campaigns:
        feedback.run(app, llm, store.get_product(app.conn, cfg.id), days=7, collect=False)
    print("learning loop done")

    app.close()
    print(f"demo home ready: {home}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/mark-demo"))
