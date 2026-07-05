"""RAG-of-winners — index top-performing posts and retrieve them as examples.

After metrics land, the top ~20% of posts (by engagement) become "winners": their
caption + hook are embedded and stored. When generating new content, the writer
pulls the most similar winners as few-shot examples, so the system converges toward
what actually works with this audience.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .. import db as db_module
from .. import vectors
from ..app import App
from ..llm import LLM


def _performance_rows(app: App, product_id: str, max_age_days: int) -> list[dict]:
    rows = db_module.query(
        app.conn,
        """
        SELECT c.id AS content_id, c.platform, c.content_type, c.caption, c.hook,
               m.engagement_rate AS engagement_rate
        FROM content c
        JOIN posts p ON p.content_id = c.id
        JOIN metrics m ON m.post_id = p.id
        WHERE c.product_id = ? AND c.status = 'posted'
          AND p.posted_at >= datetime('now', ?)
          AND m.id = (SELECT m2.id FROM metrics m2 WHERE m2.post_id = p.id
                      ORDER BY m2.collected_at DESC LIMIT 1)
        """,
        (product_id, f"-{int(max_age_days)} days"),
    )
    return [dict(r) for r in rows]


def refresh_winners(app: App, llm: LLM, product: dict, top_pct: float = 0.2,
                    max_age_days: int = 90) -> list[dict]:
    """Rebuild the winner set as the per-platform top `top_pct` of posts from the
    trailing `max_age_days` window.

    Per-platform, because a pooled top-20% hands every slot to the highest-rate
    platform and leaves X/LinkedIn with zero examples. Windowed at the source
    (posted_at), because pruning by added_at just re-inserted all-time hits on
    the next refresh — freezing the index on old taste forever.
    """
    rows = _performance_rows(app, product["id"], max_age_days)
    desired: dict[int, dict] = {}
    by_platform: dict[str, list[dict]] = {}
    for r in rows:
        by_platform.setdefault(r["platform"], []).append(r)
    for platform_rows in by_platform.values():
        platform_rows.sort(key=lambda r: r["engagement_rate"] or 0.0, reverse=True)
        k = max(1, math.ceil(len(platform_rows) * top_pct))
        for w in platform_rows[:k]:
            desired[w["content_id"]] = w

    existing = {r["content_id"] for r in db_module.query(
        app.conn,
        "SELECT w.content_id FROM winners w JOIN content c ON c.id = w.content_id "
        "WHERE c.product_id = ?", (product["id"],))}

    # Drop winners that fell out of the window or out of the top set.
    stale = existing - set(desired)
    if stale:
        db_module.execute(
            app.conn,
            f"DELETE FROM winners WHERE content_id IN ({','.join('?' * len(stale))})",
            list(stale))

    inserted = []
    for content_id, w in desired.items():
        if content_id in existing:
            continue
        text = f"{w['hook'] or ''}\n{w['caption'] or ''}".strip()
        vec = llm.embed_one(text, product_id=product["id"])
        db_module.insert(
            app.conn, "winners",
            content_id=w["content_id"], platform=w["platform"],
            content_type=w["content_type"], caption=w["caption"], hook=w["hook"],
            engagement_rate=w["engagement_rate"] or 0.0, embedding=vectors.to_blob(vec),
        )
        inserted.append(w)
    return inserted


def retrieve(app: App, llm: LLM, platform: str, query: str, k: int = 4,
             product_id: Optional[str] = None) -> list[dict]:
    """Return the top-k most similar winners (prefers same platform).

    Pass product_id to keep campaigns' example pools separate — one product's
    winning copy must never leak into another product's prompts.
    """
    if product_id:
        base = ("SELECT w.* FROM winners w JOIN content c ON c.id = w.content_id "
                "WHERE c.product_id = ?")
        rows = db_module.query(app.conn, base + " AND w.platform = ?",
                               (product_id, platform))
        if not rows:  # same-product fallback across platforms, never across products
            rows = db_module.query(app.conn, base, (product_id,))
    else:
        rows = db_module.query(
            app.conn, "SELECT * FROM winners WHERE platform = ?", (platform,))
        if not rows:
            rows = db_module.query(app.conn, "SELECT * FROM winners")
    if not rows:
        return []

    qvec = llm.embed_one(query, product_id=None)
    dim = qvec.shape[0]
    usable, embs = [], []
    for r in rows:
        vec = vectors.from_blob(r["embedding"]) if r["embedding"] else None
        if vec is None or vec.shape[0] != dim:  # skip mixed-mode embeddings
            continue
        usable.append(dict(r))
        embs.append(vec)
    if not usable:
        return []

    matrix = np.stack(embs)
    ranked = vectors.top_k(qvec, matrix, k)
    out = []
    for idx, sim in ranked:
        d = usable[idx]
        d["similarity"] = round(sim, 4)
        out.append(d)
    return out


def count(app: App, product_id: Optional[str] = None) -> int:
    if product_id:
        row = db_module.query_one(
            app.conn,
            "SELECT COUNT(*) AS n FROM winners w JOIN content c ON c.id = w.content_id "
            "WHERE c.product_id = ?", (product_id,))
    else:
        row = db_module.query_one(app.conn, "SELECT COUNT(*) AS n FROM winners")
    return row["n"] if row else 0
