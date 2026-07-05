"""Domain data-access helpers built on top of :mod:`mark.db`.

Keeps the common queries (active product, drafts, content lookups, post records)
in one place so the CLI, agents, posting, and analytics layers stay clean.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

from . import db as db_module
from .config import ProductConfig


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #
def upsert_product(conn: sqlite3.Connection, p: ProductConfig, active: bool = True) -> str:
    db_module.execute(
        conn,
        """
        INSERT INTO products (id, name, description, target_audience, brand_voice,
                              website_url, platforms, posting_cadence, strategies,
                              specificity_bank, knowledge, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, description=excluded.description,
            target_audience=excluded.target_audience, brand_voice=excluded.brand_voice,
            website_url=excluded.website_url, platforms=excluded.platforms,
            posting_cadence=excluded.posting_cadence,
            -- COALESCE: a YAML re-import without these keys must not clobber
            -- allowlists/pools curated through the app (Playbook page etc.).
            strategies=COALESCE(excluded.strategies, products.strategies),
            specificity_bank=COALESCE(excluded.specificity_bank, products.specificity_bank),
            knowledge=COALESCE(excluded.knowledge, products.knowledge)
        """,
        (p.id, p.name, p.description, p.target_audience, p.brand_voice,
         p.website_url, db_module._encode(p.platforms),
         db_module._encode(p.posting_cadence),
         db_module._encode(p.strategies) if p.strategies else None,
         db_module._encode(p.specificity_bank) if p.specificity_bank else None,
         db_module._encode(p.knowledge) if p.knowledge else None,
         1 if active else 0),
    )
    if active:
        set_active_product(conn, p.id)
    return p.id


def list_products(conn: sqlite3.Connection, include_archived: bool = False) -> list[dict]:
    where = "" if include_archived else "WHERE COALESCE(archived, 0) = 0"
    return [dict(r) for r in db_module.query(
        conn, f"SELECT * FROM products {where} ORDER BY created_at")]


def get_product(conn: sqlite3.Connection, product_id: str) -> Optional[dict]:
    return db_module.row_to_dict(
        db_module.query_one(conn, "SELECT * FROM products WHERE id = ?", (product_id,))
    )


def get_active_product(conn: sqlite3.Connection) -> Optional[dict]:
    return db_module.row_to_dict(
        db_module.query_one(
            conn, "SELECT * FROM products WHERE active = 1 ORDER BY created_at DESC LIMIT 1"
        )
    )


def set_active_product(conn: sqlite3.Connection, product_id: str) -> None:
    """CLI-style exclusive activation (one campaign selected)."""
    db_module.execute(conn, "UPDATE products SET active = 0", ())
    db_module.execute(conn, "UPDATE products SET active = 1 WHERE id = ?", (product_id,))


def set_product_active(conn: sqlite3.Connection, product_id: str, active: bool) -> None:
    """Per-campaign run toggle — multiple campaigns can run at once (web app)."""
    db_module.execute(conn, "UPDATE products SET active = ? WHERE id = ?",
                      (1 if active else 0, product_id))


def update_product(conn: sqlite3.Connection, product_id: str, **fields: Any) -> None:
    if not fields:
        return
    cols = list(fields.keys())
    encoded = [db_module._encode(v) for v in fields.values()]
    assignments = ", ".join(f"{c} = ?" for c in cols)
    db_module.execute(conn, f"UPDATE products SET {assignments} WHERE id = ?",
                      encoded + [product_id])


def archive_product(conn: sqlite3.Connection, product_id: str) -> None:
    """Soft-delete: campaign disappears from lists but content/history is kept."""
    db_module.execute(conn, "UPDATE products SET active = 0, archived = 1 WHERE id = ?",
                      (product_id,))


def resolve_product(conn: sqlite3.Connection, product_id: Optional[str]) -> Optional[dict]:
    """A product dict by id, or the active product if id is None."""
    if product_id:
        return get_product(conn, product_id)
    return get_active_product(conn)


# --------------------------------------------------------------------------- #
# Content
# --------------------------------------------------------------------------- #
def insert_content(conn: sqlite3.Connection, **fields: Any) -> int:
    return db_module.insert(conn, "content", **fields)


def get_content(conn: sqlite3.Connection, content_id: int) -> Optional[dict]:
    return db_module.row_to_dict(
        db_module.query_one(conn, "SELECT * FROM content WHERE id = ?", (content_id,))
    )


def list_content(conn: sqlite3.Connection, status: Optional[str] = None,
                 product_id: Optional[str] = None, platform: Optional[str] = None,
                 limit: int = 100) -> list[dict]:
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if product_id:
        clauses.append("product_id = ?")
        params.append(product_id)
    if platform:
        clauses.append("platform = ?")
        params.append(platform)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = db_module.query(
        conn, f"SELECT * FROM content {where} ORDER BY created_at DESC LIMIT ?",
        params + [limit],
    )
    return [dict(r) for r in rows]


def set_content_status(conn: sqlite3.Connection, content_id: int, status: str,
                       **extra: Any) -> None:
    db_module.update(conn, "content", content_id, status=status, **extra)


# --------------------------------------------------------------------------- #
# Posts + metrics
# --------------------------------------------------------------------------- #
def insert_post(conn: sqlite3.Connection, content_id: int, platform: str,
                platform_post_id: Optional[str], request_id: Optional[str]) -> int:
    return db_module.insert(
        conn, "posts", content_id=content_id, platform=platform,
        platform_post_id=platform_post_id, request_id=request_id,
    )


def list_posts(conn: sqlite3.Connection, product_id: Optional[str] = None,
               since_days: Optional[int] = None) -> list[dict]:
    clauses, params = [], []
    if product_id:
        clauses.append("c.product_id = ?")
        params.append(product_id)
    if since_days is not None:
        clauses.append("p.posted_at >= datetime('now', ?)")
        params.append(f"-{int(since_days)} days")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = db_module.query(
        conn,
        f"""
        SELECT p.*, c.product_id, c.content_type, c.caption, c.hook
        FROM posts p JOIN content c ON c.id = p.content_id
        {where}
        ORDER BY p.posted_at DESC
        """,
        params,
    )
    return [dict(r) for r in rows]


def latest_metric(conn: sqlite3.Connection, post_id: int) -> Optional[dict]:
    return db_module.row_to_dict(
        db_module.query_one(
            conn,
            "SELECT * FROM metrics WHERE post_id = ? ORDER BY collected_at DESC LIMIT 1",
            (post_id,),
        )
    )


def update_content(conn: sqlite3.Connection, content_id: int, **fields: Any) -> None:
    db_module.update(conn, "content", content_id, **fields)


def content_counts(conn: sqlite3.Connection, product_id: Optional[str] = None) -> dict[str, int]:
    """Content rows per status (queue badges / dashboard tiles)."""
    where, params = ("WHERE product_id = ?", [product_id]) if product_id else ("", [])
    rows = db_module.query(
        conn, f"SELECT status, COUNT(*) AS n FROM content {where} GROUP BY status", params)
    return {r["status"]: r["n"] for r in rows}


def list_activity(conn: sqlite3.Connection, limit: int = 50,
                  product_id: Optional[str] = None) -> list[dict]:
    where, params = ("WHERE product_id = ?", [product_id]) if product_id else ("", [])
    rows = db_module.query(
        conn, f"SELECT * FROM activity {where} ORDER BY id DESC LIMIT ?", params + [limit])
    return [dict(r) for r in rows]
