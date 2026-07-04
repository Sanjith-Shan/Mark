"""Reply drafting — first-hour comment replies, drafted for one-tap approval.

Author-reply chains are weighted enormously by ranking systems (X: ~75-150x a
like; TikTok/IG boost creator-reply velocity), and comment sections are where
lore forms. The posting API cannot post comments, so this subsystem drafts
in-voice replies the owner approves and posts manually in seconds.

Hard rules (from the research):
  * read the room — punchline on jokes, warmth on sincerity, never a pitch
  * comments about visa status, mental health, or financial desperation are
    flagged sensitive and never get an auto-draft posted without a human
  * character-fronted posts reply in the character's voice
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from . import characters as characters_mod
from . import db as db_module
from . import prompts, store
from .app import App
from .llm import LLM

SENSITIVE_MARKERS = ["visa", "sponsorship", "deported", "depress", "anxiety",
                     "suicid", "can't afford", "cant afford", "broke", "evict",
                     "homeless", "desperate", "crying", "panic"]


class ReplyDraft(BaseModel):
    reply_text: str = ""
    sensitive: bool = False   # sensitive topic — human must handle it
    skip: bool = False        # not worth replying (spam, empty, bot)
    reasoning: str = ""


class ReplyBatch(BaseModel):
    items: list[ReplyDraft] = Field(default_factory=list)


def unanswered_comments(app: App, product_id: Optional[str] = None,
                        max_age_hours: int = 48, limit: int = 20) -> list[dict]:
    """Recent comments on our posts with no reply drafted yet."""
    clauses = ["cm.collected_at >= datetime('now', ?)"]
    params: list = [f"-{int(max_age_hours)} hours"]
    if product_id:
        clauses.append("c.product_id = ?")
        params.append(product_id)
    params.append(limit)
    rows = db_module.query(
        app.conn,
        f"""
        SELECT cm.id AS comment_id, cm.comment_text, cm.author, cm.sentiment,
               p.id AS post_id, c.id AS content_id, c.product_id, c.platform,
               c.hook, c.caption, c.strategy_context
        FROM comments cm
        JOIN posts p ON p.id = cm.post_id
        JOIN content c ON c.id = p.content_id
        WHERE {' AND '.join(clauses)}
          AND NOT EXISTS (SELECT 1 FROM replies r WHERE r.comment_id = cm.id)
        ORDER BY cm.collected_at DESC LIMIT ?
        """,
        params,
    )
    return [dict(r) for r in rows]


def draft_replies(app: App, llm: LLM, product: dict, limit: int = 20) -> list[dict]:
    """Draft in-voice replies for unanswered comments. Returns drafted rows."""
    pending = unanswered_comments(app, product_id=product["id"], limit=limit)
    drafted = []
    for c in pending:
        sctx = db_module.loads(c.get("strategy_context"), {}) or {}
        character = (characters_mod.get(app, sctx["character_id"])
                     if sctx.get("character_id") else None)
        keyword_sensitive = _keyword_sensitive(c["comment_text"])

        result = llm.parse(
            prompts.reply_system(product, c["platform"], character),
            prompts.reply_user(c),
            ReplyDraft, model=app.settings.llm.text_model, temperature=0.9,
            product_id=product["id"], content_id=c["content_id"],
            mock_factory=lambda c=c: _mock_reply(c),
        )
        if result.skip and not result.reply_text.strip():
            db_module.insert(app.conn, "replies", comment_id=c["comment_id"],
                             post_id=c["post_id"], content_id=c["content_id"],
                             product_id=c["product_id"], platform=c["platform"],
                             reply_text="", sensitive=0, status="skipped")
            continue
        sensitive = 1 if (result.sensitive or keyword_sensitive) else 0
        rid = db_module.insert(
            app.conn, "replies", comment_id=c["comment_id"], post_id=c["post_id"],
            content_id=c["content_id"], product_id=c["product_id"],
            platform=c["platform"], reply_text=result.reply_text.strip(),
            sensitive=sensitive, status="draft")
        drafted.append(get(app, rid))
    if drafted:
        db_module.log_activity(app.conn, "replies",
                               f"Drafted {len(drafted)} comment replies",
                               product_id=product["id"])
    return drafted


def get(app: App, reply_id: int) -> Optional[dict]:
    row = db_module.query_one(
        app.conn,
        "SELECT r.*, cm.comment_text, cm.author FROM replies r "
        "JOIN comments cm ON cm.id = r.comment_id WHERE r.id = ?", (reply_id,))
    return db_module.row_to_dict(row)


def list_drafts(app: App, product_id: Optional[str] = None,
                status: str = "draft", limit: int = 50) -> list[dict]:
    clauses, params = ["r.status = ?"], [status]
    if product_id:
        clauses.append("r.product_id = ?")
        params.append(product_id)
    params.append(limit)
    rows = db_module.query(
        app.conn,
        f"SELECT r.*, cm.comment_text, cm.author, c.hook AS post_hook "
        f"FROM replies r JOIN comments cm ON cm.id = r.comment_id "
        f"LEFT JOIN content c ON c.id = r.content_id "
        f"WHERE {' AND '.join(clauses)} ORDER BY r.created_at DESC LIMIT ?",
        params)
    return [dict(r) for r in rows]


def set_status(app: App, reply_id: int, status: str,
               reply_text: Optional[str] = None) -> Optional[dict]:
    fields: dict = {"status": status}
    if reply_text is not None:
        fields["reply_text"] = reply_text
    db_module.update(app.conn, "replies", reply_id, **fields)
    return get(app, reply_id)


def _keyword_sensitive(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in SENSITIVE_MARKERS)


def _mock_reply(c: dict) -> ReplyDraft:
    text = (c.get("comment_text") or "").lower()
    if _keyword_sensitive(text):
        return ReplyDraft(reply_text="", sensitive=True, skip=False,
                          reasoning="offline: sensitive topic — human only")
    if "?" in text:
        return ReplyDraft(reply_text="good question — short answer: yes. longer "
                                     "answer in bio.", reasoning="offline: question")
    return ReplyDraft(reply_text="the group chat understands 🫡",
                      reasoning="offline: default warm reply")
