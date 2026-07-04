"""Judge calibration — teach the comedy judge THIS audience's taste.

LLMs are near-noise judges of funny by default (ρ≈0.2 with humans), but ranking
becomes expert-level when aligned on real audience preference data (67%→82.4%
on the New Yorker caption benchmark). Mark collects that preference signal for
free: every pair of same-platform posts with divergent engagement is a labeled
preference. This module mines those pairs and formats them as few-shot
calibration for the pairwise humor judge.
"""

from __future__ import annotations

from .. import db as db_module
from ..app import App

# A pair only counts as a real preference when the winner beat the loser by
# this engagement multiple (small gaps are noise, not taste).
MIN_DIVERGENCE = 2.0


def preference_pairs(app: App, product_id: str, platform: str,
                     limit: int = 3, days: int = 90) -> list[dict]:
    """Mine (winner, loser) post pairs from this account's own engagement.

    Same platform + content type, both measured, engagement divergence ≥ 2x.
    Most-divergent and most-recent pairs first.
    """
    rows = db_module.query(
        app.conn,
        """
        SELECT c.id, c.hook, c.caption, c.content_type, m.engagement_rate
        FROM content c
        JOIN posts p ON p.content_id = c.id
        JOIN metrics m ON m.post_id = p.id
        WHERE c.product_id = ? AND c.platform = ? AND c.status = 'posted'
          AND p.posted_at >= datetime('now', ?)
          AND m.id = (SELECT m2.id FROM metrics m2 WHERE m2.post_id = p.id
                      ORDER BY m2.collected_at DESC LIMIT 1)
        ORDER BY p.posted_at DESC
        """,
        (product_id, platform, f"-{int(days)} days"),
    )
    posts = [dict(r) for r in rows if (r["caption"] or "").strip()]
    pairs = []
    seen: set[int] = set()
    # Pair each post with the most-divergent same-type partner not yet used.
    by_type: dict[str, list[dict]] = {}
    for p in posts:
        by_type.setdefault(p["content_type"], []).append(p)
    for group in by_type.values():
        group.sort(key=lambda p: p["engagement_rate"] or 0.0, reverse=True)
        i, j = 0, len(group) - 1
        while i < j:
            hi, lo = group[i], group[j]
            if hi["id"] in seen or lo["id"] in seen:
                i, j = (i + 1, j) if hi["id"] in seen else (i, j - 1)
                continue
            hi_rate = hi["engagement_rate"] or 0.0
            lo_rate = max(lo["engagement_rate"] or 0.0, 1e-6)
            if hi_rate / lo_rate < MIN_DIVERGENCE:
                break  # remaining pairs are even closer
            pairs.append({"winner": hi, "loser": lo,
                          "ratio": round(hi_rate / lo_rate, 1)})
            seen.update((hi["id"], lo["id"]))
            i, j = i + 1, j - 1
    pairs.sort(key=lambda p: p["ratio"], reverse=True)
    return pairs[:limit]


def calibration_block(app: App, product_id: str, platform: str,
                      limit: int = 3) -> str:
    """Few-shot block for the pairwise judge: what THIS audience actually
    rewarded. Empty string until enough posted+measured history exists."""
    try:
        pairs = preference_pairs(app, product_id, platform, limit=limit)
    except Exception:
        return ""
    if not pairs:
        return ""
    lines = ["\nCALIBRATION — real preferences measured from THIS audience "
             "(weigh these heavily; they beat your priors):"]
    for p in pairs:
        w, l = p["winner"], p["loser"]
        lines.append(
            f'- PREFERRED ({p["ratio"]}x engagement): "{(w["hook"] or "").strip()[:90]}" '
            f'/// OVER: "{(l["hook"] or "").strip()[:90]}"')
    return "\n".join(lines)
