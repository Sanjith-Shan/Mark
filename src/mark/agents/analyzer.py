"""Analyzer agent — turns recent performance into actionable insights.

Runs weekly (or on demand). Produces an :class:`EngagementInsights` object that the
operator reads via `mark insights` and that documents what's working.
"""

from __future__ import annotations

from collections import defaultdict

from .. import db as db_module
from .. import prompts
from ..analytics import collector
from ..app import App
from ..llm import LLM
from ..schemas import EngagementInsights, EngagementInsightsWire


def analyze(app: App, llm: LLM, product: dict, days: int = 14,
            sentiment_summary: str = "") -> EngagementInsights:
    perf = collector.recent_performance(app, product_id=product["id"], days=days)
    table = _performance_table(perf)

    # The wire schema avoids dict[str, str] fields, which OpenAI's strict
    # structured-output mode rejects (free-form additionalProperties).
    wire = llm.parse(
        prompts.analyzer_system(product),
        prompts.analyzer_user(table, sentiment_summary or "n/a"),
        EngagementInsightsWire,
        model=app.settings.llm.text_model, temperature=0.4, product_id=product["id"],
        mock_factory=lambda: EngagementInsightsWire.from_insights(
            _mock_insights(app, product, perf, sentiment_summary)),
    )
    return wire.to_insights()


def _performance_table(perf: list[dict]) -> str:
    if not perf:
        return "(no performance data yet)"
    lines = ["platform | type | eng_rate | views | hook"]
    for r in perf[:25]:
        lines.append(f"{r['platform']} | {r['content_type']} | {r['engagement_rate']:.3f} | "
                     f"{r['views']} | {(r['hook'] or '')[:40]}")
    return "\n".join(lines)


def _mock_insights(app: App, product: dict, perf: list[dict],
                   sentiment_summary: str) -> EngagementInsights:
    if not perf:
        return EngagementInsights(
            audience_sentiment_summary=sentiment_summary or "n/a",
            raw_analysis="No posted content with metrics yet — generate, post, and collect first.",
            recommended_adjustments=["Post consistently to gather baseline data."],
        )

    # Best content type per platform (by average engagement).
    by_pt: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in perf:
        by_pt[r["platform"]][r["content_type"]].append(r["engagement_rate"])
    best_types = {p: max(types.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))[0]
                  for p, types in by_pt.items()}

    # Best hook styles from the strategy_context of top performers.
    top_ids = [r["content_id"] for r in perf[:max(3, len(perf) // 5)]]
    hook_styles, topics = _styles_and_topics(app, top_ids)
    worst_ids = [r["content_id"] for r in perf[-max(1, len(perf) // 5):]]
    _, worst_topics = _styles_and_topics(app, worst_ids)

    # Best posting times from the bandit (falls back to config).
    best_times = _best_times(app, product["id"], list(best_types.keys()))

    return EngagementInsights(
        top_performing_topics=topics[:5],
        worst_performing_topics=worst_topics[:5],
        best_hook_styles=hook_styles[:4],
        best_content_types=best_types,
        best_posting_times=best_times,
        audience_sentiment_summary=sentiment_summary or "n/a",
        recommended_adjustments=_recommendations(best_types, hook_styles),
        raw_analysis=f"Analyzed {len(perf)} posts. Top engagement "
                     f"{perf[0]['engagement_rate']:.3f} on {perf[0]['platform']}.",
    )


def _styles_and_topics(app: App, content_ids: list[int]) -> tuple[list[str], list[str]]:
    if not content_ids:
        return [], []
    qmarks = ",".join("?" for _ in content_ids)
    rows = db_module.query(
        app.conn, f"SELECT strategy_context FROM content WHERE id IN ({qmarks})", content_ids)
    styles, topics = [], []
    for r in rows:
        sctx = db_module.loads(r["strategy_context"], {}) or {}
        if sctx.get("hook_style"):
            styles.append(sctx["hook_style"])
        if sctx.get("topic"):
            topics.append(sctx["topic"])
    # Dedupe preserving order.
    return list(dict.fromkeys(styles)), list(dict.fromkeys(topics))


def _best_times(app: App, product_id: str, platforms: list[str]) -> dict[str, str]:
    out = {}
    try:
        from ..learning import bandit

        for p in platforms:
            board = [a for a in bandit.leaderboard(app, product_id, p)
                     if a["arm_type"] == "post_time"]
            if board:
                out[p] = board[0]["arm_value"]
            else:
                times = app.settings.platform(p).optimal_times
                out[p] = times[0] if times else "12:00"
    except Exception:
        pass
    return out


def _recommendations(best_types: dict, hook_styles: list[str]) -> list[str]:
    recs = []
    for platform, ctype in best_types.items():
        recs.append(f"Lean into {ctype} content on {platform}.")
    if hook_styles:
        recs.append(f"Favor '{hook_styles[0]}' hooks — they're outperforming.")
    recs.append("Double down on the top topics; retire the worst-performing ones.")
    return recs
