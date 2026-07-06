"""Humor radar — find what the internet finds funny RIGHT NOW, and ride it.

The LLM-written-joke lane is shelved until it proves itself; this is the
curation lane: watch the places where trending humor is ranked in real time,
score every sighting for funniness / copyability / safety, track velocity the
same way the trend radar does (a meme past its peak is brand damage), and turn
the best finds into repost drafts.

Sources (all free, all with graceful degradation + offline mocks):
  * Reddit meme subs, hot + rising  — the fastest broad meme signal there is
  * Tenor trending                  — what people are actually sending each
                                      other in chats (the "GIF Keyboard" app)
  * Imgflip popular templates       — which meme FORMATS are alive
  * KnowYourMeme trending           — context + names for what's spiking

Hard rules, enforced here and not negotiable:
  * ENTERTAINMENT CAMPAIGNS ONLY — a product/brand account reposting memes is
    both a copyright exposure and the documented account-killer pattern.
  * Reposts NEVER auto-approve — a human judges every one (provenance and
    taste are human calls).
  * Credit is always carried (caption + strategy_context.permalink/author).
  * Drafts expire (default 48h) — posting a dead meme late is worse than
    posting nothing.
  * NSFW / unclear-origin finds are dropped at the door.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from . import db as db_module
from . import store
from .app import App
from .llm import LLM

log = logging.getLogger("mark.humor_radar")

STRATEGY_ID = "curated-repost"  # recorded in strategy_context; bandit tracks it

# Velocity/stage math mirrors trends/aggregator.py — same discipline.
_VEL_MIN_AGE_H, _VEL_MAX_AGE_H, _STAGE_EPS = 2, 48, 0.03


# --------------------------------------------------------------------------- #
# Sources — each returns [{external_id, title, media_url, media_type,
#                          permalink, author, community, raw_score, metadata}]
# --------------------------------------------------------------------------- #
_IMG_RE = re.compile(r"\.(jpg|jpeg|png|gif|webp)$", re.IGNORECASE)

_MOCK_FINDS = [
    ("mock-1", "when the wifi drops for 0.5 seconds and you check the router, "
               "your phone, and your will to live", 78),
    ("mock-2", "nobody: — my brain at 3am: remember that thing from 2016", 74),
    ("mock-3", "me explaining to my mom why the guy screaming at a lettuce "
               "is funny", 70),
    ("mock-4", "POV: you said 'you too' when the waiter said enjoy your meal", 66),
]


def fetch_reddit(app: App, subreddits: list[str], limit: int = 25) -> list[dict]:
    """Hot + rising image/gif posts from meme subs. NSFW and stickied skipped."""
    if app.force_mock:
        return [{"source": "reddit", "external_id": eid, "title": t,
                 "media_url": f"mock://{eid}.png", "media_type": "image",
                 "permalink": f"https://reddit.com/{eid}", "author": "u/mockuser",
                 "community": "r/memes", "raw_score": float(s),
                 "metadata": {"fallback": True}} for eid, t, s in _MOCK_FINDS]
    from .trends import reddit as reddit_client

    out = []
    per = max(4, limit // max(len(subreddits), 1))
    for i, sub in enumerate(subreddits):
        # OAuth listing when creds exist (real upvote velocity)…
        children = reddit_client.get_listing(sub, "hot", limit=per * 2)
        if children is not None:
            for d in children:
                if d.get("stickied") or d.get("over_18"):
                    continue
                url = d.get("url_overridden_by_dest") or d.get("url") or ""
                if not _IMG_RE.search(url):
                    continue  # v1: images/gifs (reddit video = split streams)
                title = (d.get("title") or "").strip()
                if not title:
                    continue
                ups = int(d.get("ups") or 0)
                created = d.get("created_utc") or (time.time() - 3600)
                age_h = max(time.time() - created, 900) / 3600
                score = min(100.0, (ups / age_h) / 8.0)  # ~800 ups/h → 100
                out.append({
                    "source": "reddit",
                    "external_id": f"reddit:{d.get('id')}",
                    "title": title[:200],
                    "media_url": url,
                    "media_type": "gif" if url.lower().endswith(".gif") else "image",
                    "permalink": f"https://reddit.com{d.get('permalink', '')}",
                    "author": f"u/{d.get('author', '?')}",
                    "community": f"r/{sub}",
                    "raw_score": round(score, 1),
                    "metadata": {"ups": ups, "age_hours": round(age_h, 1)},
                })
            continue
        # …else the anonymous Atom feed, politely paced, rank-scored.
        if i > 0:
            time.sleep(reddit_client._RSS_PACING_S)
        for e in (reddit_client.get_rss(sub, "hot") or [])[:per]:
            if not e.get("image_url"):
                continue
            out.append({
                "source": "reddit",
                "external_id": f"reddit:{e['id']}",
                "title": e["title"][:200],
                "media_url": e["image_url"],
                "media_type": "gif" if e["image_url"].lower().endswith(".gif") else "image",
                "permalink": e.get("permalink"),
                "author": e.get("author"),
                "community": f"r/{sub}",
                "raw_score": round(max(20.0, 80.0 - e["rank"] * 3.0), 1),
                "metadata": {"rss": True, "rank": e["rank"]},
            })
    return out


# Tenor v2 needs a Google API key (env TENOR_API_KEY); the legacy v1 endpoint
# still answers with the long-public test key. Both are best-effort.
def fetch_tenor(app: App, limit: int = 15) -> list[dict]:
    if app.force_mock:
        return [{"source": "tenor", "external_id": "tenor-mock-1",
                 "title": "trending reaction: side-eye cat", "media_url": None,
                 "media_type": "gif", "permalink": "https://tenor.com",
                 "author": None, "community": "tenor trending",
                 "raw_score": 72.0, "metadata": {"fallback": True}}]
    import os

    try:
        import httpx

        key = os.environ.get("TENOR_API_KEY")
        with httpx.Client(timeout=12) as client:
            if key:
                resp = client.get("https://tenor.googleapis.com/v2/featured",
                                  params={"key": key, "limit": str(limit),
                                          "media_filter": "gif,mp4"})
            else:
                resp = client.get("https://g.tenor.com/v1/trending",
                                  params={"key": "LIVDSRZULELA", "limit": str(limit)})
            resp.raise_for_status()
            data = resp.json()
        out = []
        results = data.get("results") or []
        n = max(len(results), 1)
        for i, r in enumerate(results):
            gid = str(r.get("id") or "")
            title = (r.get("content_description") or r.get("title") or
                     r.get("h1_title") or "").strip()
            media = None
            fmts = r.get("media_formats") or {}
            if fmts:
                media = (fmts.get("gif") or fmts.get("mp4") or {}).get("url")
            else:
                for m in (r.get("media") or []):
                    media = (m.get("gif") or m.get("mp4") or {}).get("url")
                    if media:
                        break
            if not gid or not title:
                continue
            out.append({
                "source": "tenor", "external_id": f"tenor:{gid}",
                "title": title[:200], "media_url": media, "media_type": "gif",
                "permalink": r.get("itemurl") or r.get("url"),
                "author": None, "community": "tenor trending",
                "raw_score": round(80 - i * (40 / n), 1),  # rank-derived
                "metadata": {},
            })
        return out
    except Exception as exc:
        log.warning("tenor fetch failed: %s", exc)
        return []


def fetch_imgflip_templates(app: App, limit: int = 10) -> list[dict]:
    """Which meme FORMATS are alive (not postable media — creative direction)."""
    from .trends import imgflip

    out = []
    for t in imgflip.fetch(app, limit=limit):
        name = t["topic"].removeprefix("meme template: ")
        out.append({
            "source": "imgflip", "external_id": f"imgflip:{name.lower()}",
            "title": f"format alive: {name}", "media_url": None,
            "media_type": "template", "permalink": "https://imgflip.com/memetemplates",
            "author": None, "community": "imgflip popular",
            "raw_score": float(t["raw_score"]),
            "metadata": t.get("metadata") or {},
        })
    return out


def fetch_kym(app: App, limit: int = 8) -> list[dict]:
    """KnowYourMeme trending page (best-effort scrape) — names + context for
    what's spiking, which also powers the safety judgment."""
    if app.force_mock:
        return []
    try:
        import httpx

        # /memes/trending 404s now; the homepage and /memes/popular both carry
        # the current trending set as /memes/<slug> links.
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            resp = client.get("https://knowyourmeme.com/memes/popular",
                              headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                resp = client.get("https://knowyourmeme.com/",
                                  headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            html = resp.text
        slugs = re.findall(r'href="/memes/(?!popular|trending|all|submissions)'
                           r'([a-z0-9][a-z0-9-]{2,60})"', html)
        seen, out = set(), []
        for slug in slugs:
            if slug in seen:
                continue
            seen.add(slug)
            name = slug.replace("-", " ")
            out.append({
                "source": "kym", "external_id": f"kym:{slug}",
                "title": f"meme trending: {name}", "media_url": None,
                "media_type": "template",
                "permalink": f"https://knowyourmeme.com/memes/{slug}",
                "author": None, "community": "knowyourmeme",
                "raw_score": 65.0, "metadata": {},
            })
            if len(out) >= limit:
                break
        return out
    except Exception as exc:
        log.warning("kym fetch failed: %s", exc)
        return []


# --------------------------------------------------------------------------- #
# Judge — is this actually funny, copyable, and safe to touch?
# --------------------------------------------------------------------------- #
class _HumorVerdict(BaseModel):
    external_id: str = ""
    funny: float = 0.5        # 0..1 — would a normal person actually laugh/share
    copyability: float = 0.5  # 0..1 — self-contained; works without source context
    safe: bool = True         # False: nsfw, tragedy-adjacent, in-joke theft, unclear origin


class _HumorVerdicts(BaseModel):
    items: list[_HumorVerdict] = Field(default_factory=list)


def _judge(app: App, llm: LLM, finds: list[dict]) -> dict[str, _HumorVerdict]:
    def _mock() -> _HumorVerdicts:
        # Offline heuristic: popularity is the only signal available.
        return _HumorVerdicts(items=[
            _HumorVerdict(external_id=f["external_id"],
                          funny=round(min(0.95, 0.35 + f["raw_score"] / 140), 3),
                          copyability=0.7 if f.get("media_url") else 0.45,
                          safe=True)
            for f in finds])

    if llm.mock or not finds:
        verdicts = _mock()
    else:
        listing = "\n".join(
            f'- id={f["external_id"]!r} [{f["source"]}/{f.get("community")}] "{f["title"]}"'
            for f in finds[:40])
        system = (
            "You rate humor sighted on the internet for a curation system that "
            "reposts the funniest current material (with credit) to a pure "
            "entertainment account.\n"
            "For each item: funny (0..1 — would a normal scroller actually laugh "
            "or send this; punish stale formats, niche in-jokes, and engagement "
            "bait), copyability (0..1 — does it work standalone for a general "
            "audience without the source thread's context), and safe (false for "
            "anything NSFW-adjacent, tragedy-derived, targeting real people, or "
            "of unclear/appropriative origin — when unsure, false).")
        verdicts = llm.parse(system, f"Rate these:\n{listing}", _HumorVerdicts,
                             model=app.settings.llm.judge_model, temperature=0.2,
                             mock_factory=_mock)
    return {v.external_id: v for v in verdicts.items}


# --------------------------------------------------------------------------- #
# Velocity + stage (same longitudinal discipline as the trend radar)
# --------------------------------------------------------------------------- #
def _velocity(app: App, external_id: str, raw_now: float) -> Optional[float]:
    rows = db_module.query(
        app.conn,
        "SELECT raw_score FROM humor_finds WHERE external_id = ? "
        "AND collected_at >= datetime('now', ?) AND collected_at <= datetime('now', ?)",
        (external_id, f"-{_VEL_MAX_AGE_H} hours", f"-{_VEL_MIN_AGE_H} hours"))
    prior = [r["raw_score"] for r in rows if r["raw_score"] is not None]
    if not prior:
        return None
    return round((raw_now - sum(prior) / len(prior)) / 100.0, 4)


def _stage(velocity: Optional[float], raw_now: float) -> str:
    if velocity is None:
        return "mature" if raw_now >= 85 else "new"
    if velocity > _STAGE_EPS:
        return "rising"
    if velocity < -_STAGE_EPS:
        return "declining"
    return "mature"


# --------------------------------------------------------------------------- #
# Refresh — the collection pass (wired into the fast trend poll)
# --------------------------------------------------------------------------- #
def refresh(app: App, llm: LLM, limit_per_source: int = 20) -> list[dict]:
    cfg = app.settings.humor_radar
    if not cfg.enabled:
        return []
    raw = (fetch_reddit(app, list(cfg.subreddits), limit=limit_per_source)
           + fetch_tenor(app, limit=min(limit_per_source, 15))
           + fetch_imgflip_templates(app, limit=10)
           + fetch_kym(app, limit=8))
    # Dedupe within the batch by external_id (hot + rising overlap).
    merged: dict[str, dict] = {}
    for f in raw:
        cur = merged.get(f["external_id"])
        if cur is None or f["raw_score"] > cur["raw_score"]:
            merged[f["external_id"]] = f
    finds = list(merged.values())
    if not finds:
        return []

    verdicts = _judge(app, llm, finds)
    stored = []
    for f in finds:
        v = verdicts.get(f["external_id"], _HumorVerdict())
        vel = _velocity(app, f["external_id"], f["raw_score"])
        stage = _stage(vel, f["raw_score"])
        db_module.insert(
            app.conn, "humor_finds",
            source=f["source"], external_id=f["external_id"], title=f["title"],
            media_url=f.get("media_url"), media_type=f.get("media_type"),
            permalink=f.get("permalink"), author=f.get("author"),
            community=f.get("community"), raw_score=f["raw_score"],
            funny=round(v.funny, 3), copyability=round(v.copyability, 3),
            safe=1 if v.safe else 0, velocity=vel, stage=stage,
            metadata=f.get("metadata") or {})
        stored.append({**f, "funny": v.funny, "copyability": v.copyability,
                       "safe": v.safe, "velocity": vel, "stage": stage})
    purge_old(app)
    stored.sort(key=lambda x: x["funny"], reverse=True)
    return stored


def purge_old(app: App, days: int = 7) -> int:
    cur = db_module.execute(
        app.conn, "DELETE FROM humor_finds WHERE collected_at < datetime('now', ?)",
        (f"-{int(days)} days",))
    return cur.rowcount


# --------------------------------------------------------------------------- #
# The radar read side — what should we post RIGHT NOW?
# --------------------------------------------------------------------------- #
def radar(app: App, llm: Optional[LLM] = None, campaign: Optional[dict] = None,
          limit: int = 12, max_age_hours: int = 24) -> list[dict]:
    """Ranked copyworthy humor: latest sighting per item, unsafe and declining
    vetoed, blended score = funny + copyability + momentum (+ theme fit when a
    campaign is given, via embedding similarity)."""
    rows = db_module.query(
        app.conn,
        "SELECT * FROM humor_finds WHERE collected_at >= datetime('now', ?) "
        "ORDER BY collected_at DESC",
        (f"-{int(max_age_hours)} hours",))
    latest: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        latest.setdefault(d["external_id"], d)

    fit_scores: dict[str, float] = {}
    if campaign is not None and llm is not None and latest:
        try:
            import numpy as np

            from . import vectors

            items = list(latest.values())
            texts = [f"{campaign['name']} {campaign['description'][:200]}"] \
                + [i["title"] for i in items]
            vecs = llm.embed(texts, product_id=campaign["id"])
            sims = vectors.cosine_to_matrix(vecs[0], vecs[1:])
            for item, sim in zip(items, np.asarray(sims).ravel()):
                fit_scores[item["external_id"]] = float(sim)
        except Exception:
            fit_scores = {}

    out = []
    for d in latest.values():
        if not d.get("safe"):
            continue
        if (d.get("stage") or "new") == "declining":
            continue  # the window is closed — hard veto, same as trends
        d["metadata"] = db_module.loads(d.get("metadata"), {}) or {}
        momentum = max(0.0, min((d.get("velocity") or 0.0) + 0.05, 0.3)) / 0.3
        fit = fit_scores.get(d["external_id"])
        score = (0.45 * (d.get("funny") or 0.5)
                 + 0.2 * (d.get("copyability") or 0.5)
                 + 0.2 * momentum
                 + (0.15 * max(fit, 0.0) if fit is not None else 0.0))
        d["radar_score"] = round(score, 4)
        d["post_now"] = bool((d.get("stage") in ("new", "rising"))
                             and (d.get("funny") or 0) >= 0.6
                             and d.get("media_url"))
        out.append(d)
    out.sort(key=lambda x: x["radar_score"], reverse=True)
    return out[:limit]


# --------------------------------------------------------------------------- #
# Acting on a find — the repost draft
# --------------------------------------------------------------------------- #
def _download_media(app: App, find: dict, product_id: str, content_id: int) -> Optional[str]:
    url = find.get("media_url")
    if not url:
        return None
    from .agents.media import media_dir_for

    out_dir = media_dir_for(app, product_id, content_id)
    ext = (Path(url.split("?")[0]).suffix or ".jpg").lower()
    path = out_dir / f"{content_id}_repost{ext}"
    if app.force_mock or url.startswith("mock"):
        # Offline: a real placeholder file so the posting path is exercised.
        from PIL import Image

        Image.new("RGB", (1080, 1080), (24, 26, 34)).save(path.with_suffix(".png"))
        return str(path.with_suffix(".png"))
    try:
        import httpx

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            path.write_bytes(resp.content)
        return str(path)
    except Exception as exc:
        log.warning("media download failed for %s: %s", find["external_id"], exc)
        return None


def draft_repost(app: App, llm: LLM, product: dict, find_id: int,
                 platform: str = "x") -> dict:
    """Create a repost draft from a humor find. Entertainment campaigns ONLY;
    the draft never self-approves and expires with the meme's window."""
    from . import strategies

    if not strategies.is_entertainment(product):
        raise ValueError(
            "curated reposts are for entertainment campaigns only — a brand "
            "account reposting memes is a copyright exposure and the documented "
            "account-killer pattern (create the campaign with kind=entertainment)")
    row = db_module.query_one(app.conn, "SELECT * FROM humor_finds WHERE id = ?",
                              (find_id,))
    if not row:
        raise ValueError(f"humor find {find_id} not found")
    find = dict(row)
    if not find.get("safe"):
        raise ValueError("this find failed the safety judgment — not usable")
    if not find.get("media_url"):
        raise ValueError("this find is a format/template signal, not postable media")

    credit = find.get("author") or find.get("community") or find.get("source")
    # Caption: dry, minimal, lowercase — curation voice, not commentary. The
    # LLM-joke lane is shelved, so no rewriting of the humor itself.
    caption = f"{find['title'].strip().rstrip('.')}".lower()
    if len(caption) > 200:
        caption = caption[:199].rstrip() + "…"
    caption += f"\n\n🎥 {credit}"

    cfg = app.settings.humor_radar
    sctx = {
        "strategy": STRATEGY_ID, "strategy_name": "Curated repost",
        "humor_source": find["source"], "humor_find_id": find["id"],
        "external_id": find["external_id"], "permalink": find.get("permalink"),
        "author": find.get("author"), "community": find.get("community"),
        "funny": find.get("funny"), "stage": find.get("stage"),
        "emotional_target": "dark_laughter", "policy": "curated",
    }
    content_id = store.insert_content(
        app.conn, product_id=product["id"], platform=platform,
        content_type="image", caption=caption, hashtags=[],
        hook=find["title"][:80], media_paths=[], media_urls=[],
        strategy_context=sctx, status="draft")
    media_path = _download_media(app, find, product["id"], content_id)
    store.update_content(
        app.conn, content_id,
        media_paths=[media_path] if media_path else [],
        error=None if media_path else "media download failed — attach manually")
    db_module.execute(
        app.conn, "UPDATE content SET expires_at = datetime('now', ?) WHERE id = ?",
        (f"+{int(cfg.draft_ttl_hours)} hours", content_id))
    db_module.log_activity(
        app.conn, "humor_radar",
        f"Drafted repost of {find['external_id']} ({find.get('community')}) for {platform}",
        product_id=product["id"], content_id=content_id, level="success")
    return store.get_content(app.conn, content_id)


def _drafts_today(app: App, product_id: str) -> int:
    row = db_module.query_one(
        app.conn,
        "SELECT COUNT(*) AS n FROM content WHERE product_id = ? "
        "AND strategy_context LIKE '%curated-repost%' "
        "AND date(created_at) = date('now')", (product_id,))
    return row["n"] if row else 0


def auto_draft(app: App, llm: LLM, product: dict) -> list[dict]:
    """Scheduler hook: draft the best fresh finds for an entertainment campaign
    (drafts only — approval stays human, always)."""
    from . import strategies

    cfg = app.settings.humor_radar
    if not (cfg.enabled and cfg.auto_draft and strategies.is_entertainment(product)):
        return []
    budget = max(0, int(cfg.max_drafts_per_day) - _drafts_today(app, product["id"]))
    if budget == 0:
        return []
    drafted = []
    already = _drafted_external_ids(app, product["id"])
    for find in radar(app, llm, campaign=product, limit=10):
        if len(drafted) >= budget:
            break
        if not find["post_now"] or (find.get("funny") or 0) < cfg.min_funny:
            continue
        if find["external_id"] in already:
            continue
        try:
            platform = _best_platform(app, product)
            drafted.append(draft_repost(app, llm, product, find["id"], platform))
        except Exception as exc:
            log.warning("auto-draft failed for %s: %s", find["external_id"], exc)
    return drafted


def _drafted_external_ids(app: App, product_id: str, days: int = 7) -> set[str]:
    rows = db_module.query(
        app.conn,
        "SELECT strategy_context FROM content WHERE product_id = ? "
        "AND created_at >= datetime('now', ?) AND strategy_context LIKE '%external_id%'",
        (product_id, f"-{int(days)} days"))
    out = set()
    for r in rows:
        sctx = db_module.loads(r["strategy_context"], {}) or {}
        if sctx.get("external_id"):
            out.add(sctx["external_id"])
    return out


# Meme reposts belong where meme culture lives; never LinkedIn (professional
# feed), never Bluesky (AI/repost-hostile community, permanent blocklists).
_REPOST_PLATFORMS = ["x", "instagram", "threads", "tiktok"]


def _best_platform(app: App, product: dict) -> str:
    from . import pipeline

    enabled = [p for p in pipeline.product_platforms(product)
               if app.settings.platform(p).enabled]
    for p in _REPOST_PLATFORMS:
        if p in enabled:
            return p
    return enabled[0] if enabled else "x"
