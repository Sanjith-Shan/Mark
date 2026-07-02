"""Comment sentiment analysis (OpenAI, with an offline heuristic)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .. import db as db_module
from ..app import App
from ..llm import LLM
from ..schemas import SentimentResult

_POSITIVE = {"love", "great", "amazing", "awesome", "best", "perfect", "thank",
             "helpful", "good", "nice", "yes", "need", "want", "🔥", "❤️", "😍"}
_NEGATIVE = {"hate", "bad", "worst", "terrible", "scam", "broken", "useless",
             "annoying", "spam", "no", "stop", "ugh", "😡", "👎"}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def classify_one(app: App, llm: LLM, text: str) -> SentimentResult:
    if app.is_mock("openai"):
        return _heuristic(text)
    return llm.parse(
        "Classify the sentiment of this social media comment as positive, negative, "
        "or neutral, with a score from -1 (very negative) to 1 (very positive).",
        text, SentimentResult, model=app.settings.llm.judge_model, temperature=0.0,
        mock_factory=lambda: _heuristic(text),
    )


def _heuristic(text: str) -> SentimentResult:
    t = text.lower()
    pos = sum(1 for w in _POSITIVE if w in t)
    neg = sum(1 for w in _NEGATIVE if w in t)
    if pos > neg:
        return SentimentResult(sentiment="positive", score=min(0.2 + 0.2 * pos, 1.0))
    if neg > pos:
        return SentimentResult(sentiment="negative", score=max(-0.2 - 0.2 * neg, -1.0))
    return SentimentResult(sentiment="neutral", score=0.0)


def analyze_unscored(app: App, llm: LLM, product_id: Optional[str] = None) -> int:
    """Classify any comments missing a sentiment. Returns how many were processed."""
    clause = "WHERE cm.sentiment IS NULL"
    params: list = []
    if product_id:
        clause += " AND c.product_id = ?"
        params.append(product_id)
    rows = db_module.query(
        app.conn,
        f"SELECT cm.id, cm.comment_text FROM comments cm "
        f"JOIN posts p ON p.id = cm.post_id JOIN content c ON c.id = p.content_id {clause}",
        params,
    )
    for r in rows:
        res = classify_one(app, llm, r["comment_text"])
        db_module.update(app.conn, "comments", r["id"],
                         sentiment=res.sentiment, sentiment_score=res.score,
                         analyzed_at=_now())
    return len(rows)


def summarize(app: App, product_id: Optional[str] = None) -> str:
    clause = ""
    params: list = []
    if product_id:
        clause = ("JOIN posts p ON p.id = comments.post_id "
                  "JOIN content c ON c.id = p.content_id WHERE c.product_id = ?")
        params.append(product_id)
    rows = db_module.query(
        app.conn,
        f"SELECT sentiment, COUNT(*) AS n FROM comments {clause} GROUP BY sentiment",
        params,
    )
    if not rows:
        return "No comments collected yet."
    total = sum(r["n"] for r in rows)
    parts = [f"{r['sentiment'] or 'unscored'}: {round(100 * r['n'] / total)}%" for r in rows]
    return f"{total} comments — " + ", ".join(parts)
