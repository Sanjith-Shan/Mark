"""Content-generation pipeline tests (offline)."""

from pathlib import Path

from mark import pipeline, store
from mark.agents import writer
from mark.media import images
from mark.schemas import ContentDraft, ContentPlan


def test_generate_image_post(app, llm, product):
    row = pipeline.generate_one(app, llm, product, "instagram")
    assert row["status"] in ("draft", "approved")
    assert row["caption"]
    media = __import__("mark").db.loads(row["media_paths"], [])
    # instagram first piece may be image or carousel (video falls back to image offline).
    assert media, "expected at least one media file"
    assert all(Path(m).exists() for m in media)


def test_generate_text_post_has_no_media(app, llm, product):
    row = pipeline.generate_one(app, llm, product, "linkedin")
    assert row["caption"]
    # linkedin can be text/image/carousel; if text, media is empty.
    if row["content_type"] == "text":
        assert __import__("mark").db.loads(row["media_paths"], []) == []


def test_novelty_guard_flags_duplicate(app, llm, product):
    store.insert_content(
        app.conn, product_id=product["id"], platform="x", content_type="text",
        caption="We automate the boring parts of building so you can ship.",
        hashtags=[], hook="Stop wasting hours.", media_paths=[], status="posted")
    dup = ContentDraft(caption="We automate the boring parts of building so you can ship.",
                       hook="Stop wasting hours.")
    nov = pipeline.check_novelty(app, llm, product, "x", dup)
    assert nov.ok is False
    assert nov.max_sim >= app.settings.llm.novelty_threshold


def test_writer_finalize_trims_hashtags_and_caps_length(app, product):
    plan = ContentPlan(platform="x", content_type="text", topic="t", angle="a",
                       hook_style="question", tone="funny")
    draft = ContentDraft(caption="x" * 400, hashtags=[f"#{i}" for i in range(20)],
                         hook="Short hook here")
    out = writer._finalize(draft, app, "x", plan)
    assert len(out.hashtags) <= app.settings.platform("x").hashtag_count
    assert len(out.caption) <= 280


def test_mock_image_has_correct_size(app, llm, tmp_path):
    out = tmp_path / "img.png"
    images.generate_image(app, llm, "a bold visual", out, size="1024x1536")
    from PIL import Image

    assert out.exists()
    assert Image.open(out).size == (1024, 1536)


def test_anti_slop_critique_strips_banned_phrases():
    cleaned, removed = writer._strip_slop("This is a game-changer that will take your work to the next level.")
    assert "game-changer" not in cleaned.lower()
    assert removed
