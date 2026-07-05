"""Campaign onboarding pipeline — point Mark at ANY new product or entertainment
theme and it researches + generates the full campaign config automatically
(vision #8: the repeatable version of what was hand-curated for SudoApply).

One LLM call produces the whole campaign plan: sharpened positioning, a rich
audience model, the knowledge pools (specificity bank, pain veins, take pool),
per-campaign trend radar sources, domain-specific rewrites of every fitting
strategy brief, and an AI-ambassador character concept. The plan is then applied
in one pass: product row upserted, character created with lore initialized, and
a YAML snapshot written to ``config/products/<id>.yaml`` so the campaign stays
inspectable and hand-editable.

HARD RULE: ``fact_base`` is ALWAYS left empty by onboarding. The educational
strategy may only cite claims from the fact base, and facts must be
human-verified before they enter it — an LLM inventing "research" at onboarding
time is exactly the failure mode the rule exists to prevent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from . import characters as characters_mod
from . import db as db_module
from . import store
from . import strategies as strategies_mod
from .app import App
from .config import ProductConfig
from .llm import LLM

KNOWN_PLATFORMS = ["tiktok", "instagram", "x", "linkedin", "youtube", "bluesky", "threads"]
CONTENT_RATINGS = ("clean", "standard", "edgy")


# --------------------------------------------------------------------------- #
# Wire schemas — typed lists only (OpenAI strict structured outputs reject
# free-key dicts; see schemas.EngagementInsightsWire for the pattern).
# --------------------------------------------------------------------------- #
class CadenceItem(BaseModel):
    platform: str
    per_day: int = 1


class StrategyBriefWire(BaseModel):
    strategy_id: str
    strategist_brief: str = ""
    writer_brief: str = ""
    media_brief: str = ""
    example_sketch: str = ""


class CharacterConceptWire(BaseModel):
    name: str
    role: str = "ambassador"
    persona: str = ""       # paragraph: flaw that generates infinite episodes + off-screen antagonist
    visual_desc: str = ""   # deliberately synthetic, one signature visual anchor prop
    catchphrases: list[str] = Field(default_factory=list)


class CampaignPlanWire(BaseModel):
    """The full onboarding plan, as the LLM returns it."""

    id_slug: str
    name: str
    kind: str = "product"                 # "product" | "entertainment"
    description: str = ""                 # 2-3 sentences, sharpened
    target_audience: str = ""             # who, age, where they hang out, what they feel
    brand_voice: str = ""
    content_rating: str = "standard"      # "clean" | "standard" | "edgy"
    platforms: list[str] = Field(default_factory=list)
    posting_cadence: list[CadenceItem] = Field(default_factory=list)
    specificity_bank: list[str] = Field(default_factory=list)   # 8-12 lived artifacts
    pain_veins: list[str] = Field(default_factory=list)         # 5-8
    take_pool: list[str] = Field(default_factory=list)          # 4-6 systems/processes only
    trend_subreddits: list[str] = Field(default_factory=list)   # 4-6 real subreddit names
    trend_keywords: list[str] = Field(default_factory=list)     # 3-5
    strategy_briefs: list[StrategyBriefWire] = Field(default_factory=list)
    character_concept: CharacterConceptWire = Field(
        default_factory=lambda: CharacterConceptWire(name="Mascot"))


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
def _catalog_block() -> str:
    """The base strategy catalog, with each SudoApply-tuned strategist brief shown
    as a STYLE EXAMPLE of the density of concrete detail a rewrite must match."""
    lines = []
    for s in strategies_mod.STRATEGIES:
        tag = "  [requires a real product — SKIP for entertainment campaigns]" if s.requires_product else ""
        lines.append(
            f"### {s.id} — {s.name}{tag}\n"
            f"What it is: {s.description}\n"
            f"STYLE EXAMPLE (the current SudoApply-tuned strategist brief — match this "
            f"density of concrete, domain-specific detail): {s.strategist_brief or '—'}"
        )
    return "\n\n".join(lines)


def _system_prompt() -> str:
    return f"""You are the campaign architect for Mark, an autonomous AI marketing engine.
Given a one-paragraph description of a new product or entertainment theme, produce the
COMPLETE campaign plan that a top-tier social team would build after a week of research.

Rules:
- kind: "product" if it's a sellable product/app/service; "entertainment" if the content
  itself is the point (the account IS the business).
- description: sharpen to 2-3 sentences. No marketing adjectives.
- target_audience: a rich paragraph — who they are, age, where they hang out online,
  and what they FEEL (frustrations, aspirations, in-jokes).
- brand_voice: a paragraph, concrete enough that a writer could imitate it immediately.
- content_rating: pick "clean", "standard", or "edgy" — whatever fits the audience.
- platforms: choose from {', '.join(KNOWN_PLATFORMS)}. posting_cadence: one entry per platform.
- specificity_bank: 8-12 HYPER-concrete lived artifacts of the audience's life
  (named tools, verbatim phrasings, precise absurd numbers — never categories).
- pain_veins: 5-8 narrow pains the audience would comment "same" on.
- take_pool: 4-6 whitelisted contrarian targets — systems and processes ONLY,
  never people or named companies.
- trend_subreddits: 4-6 REAL subreddit names for this niche (no "r/" prefix).
  trend_keywords: 3-5 search terms for trend monitoring.
- strategy_briefs: for EVERY base strategy below that fits this campaign, rewrite
  strategist_brief / writer_brief / media_brief / one example_sketch domain-specifically,
  with the same density of concrete detail as the SudoApply style examples.
  Skip strategies marked "requires a real product" when kind is entertainment.
- character_concept: an AI-ambassador character. The persona paragraph MUST include a
  flaw that generates infinite episodes and a recurring OFF-SCREEN antagonist. The
  visual_desc MUST be deliberately synthetic (never photoreal) and include ONE signature
  visual anchor prop. 2-4 catchphrases.
- NEVER invent facts, statistics, or research claims anywhere in the plan.

BASE STRATEGY CATALOG:
{_catalog_block()}
"""


# --------------------------------------------------------------------------- #
# Deterministic offline mock
# --------------------------------------------------------------------------- #
_ENTERTAINMENT_HINTS = ("entertainment", "comedy", "sketch", "skit", "show", "lore",
                        "meme", "character", "cartoon", "storytelling", "episode")
_PRODUCT_HINTS = ("app", "tool", "platform", "saas", "product", "service", "extension",
                  "software", "subscription")


def slugify(text: str) -> str:
    out = "".join(ch if ch.isalnum() else "-" for ch in (text or "").lower())
    out = "-".join(part for part in out.split("-") if part)
    return out[:40] or "campaign"


def _infer_kind(description: str) -> str:
    d = (description or "").lower()
    if any(h in d for h in _ENTERTAINMENT_HINTS) and not any(h in d for h in _PRODUCT_HINTS):
        return "entertainment"
    return "product"


def _first_sentence(text: str) -> str:
    t = " ".join((text or "").split())
    for sep in (". ", "! ", "? "):
        if sep in t:
            return t.split(sep)[0] + sep[0]
    return t


def _mock_plan(description: str, name: Optional[str], kind: Optional[str],
               platforms: Optional[list[str]]) -> CampaignPlanWire:
    """Deterministic offline plan derived from the description text. Structured
    like the real thing so the whole apply path (and the tests) exercise it."""
    desc = " ".join((description or "a new thing").split())
    words = [w.strip(",.!?:;\"'()").lower() for w in desc.split()]
    keywords = [w for w in words if len(w) > 3][:6] or ["niche"]
    display_name = name or " ".join(w.capitalize() for w in desc.split()[:2])
    k = kind or _infer_kind(desc)
    plats = platforms or ["tiktok", "x"]
    kw = keywords + ["life", "daily", "grind", "world", "scene", "crowd"]

    bank = [
        f"the {kw[0]} tab that has been open for three weeks",
        f"explaining {kw[0]} to a relative at dinner for the fourth time",
        f"the group chat that only wakes up when {kw[1]} goes wrong",
        f"a 47-item to-do list where item 1 is 'figure out {kw[0]}'",
        f"the tutorial video paused at 2:13 since Tuesday",
        f"refreshing the same {kw[2]} page like it's a tracking number",
        f"the 'quick question' about {kw[0]} that takes 40 minutes",
        f"pretending to understand {kw[3]} in front of people who clearly do",
        "the 2am search history nobody should ever see",
        f"the abandoned {kw[1]} attempt from January, still installed",
    ]
    pains = [
        f"starting {kw[0]} over from scratch for the third time",
        f"everyone online seems effortlessly good at {kw[1]}",
        f"the gap between the {kw[0]} tutorial and reality",
        f"paying for tools that make {kw[2]} feel harder",
        "advice that boils down to 'just be consistent'",
        f"the {kw[3]} plateau nobody warns you about",
    ]
    takes = [
        "beginner advice that predates the internet",
        "gatekeeping dressed up as 'standards'",
        f"the {kw[0]} industrial complex of paid courses",
        "engagement-bait 'hot takes' that help no one",
    ]
    briefs = []
    for s in strategies_mod.STRATEGIES:
        if k == "entertainment" and s.requires_product:
            continue
        briefs.append(StrategyBriefWire(
            strategy_id=s.id,
            strategist_brief=(f"For {display_name}: pick ONE hyper-specific {kw[0]} moment "
                              f"(a timestamp, a named tool, a precise absurd number) — never "
                              f"a category. Mine the audience's {kw[1]} frustrations."),
            writer_brief=(f"Stay in {display_name}'s voice: casual, specific, zero marketing "
                          f"language. ≥1 concrete artifact of {kw[0]} life per post. "
                          "End on the punch."),
            media_brief=(f"Native-feeling visuals for the {kw[0]} niche — raw over polished, "
                         "never stock-photo energy."),
            example_sketch=(f'"day 14 of {kw[0]}. the {kw[1]} won again." — deadpan, '
                            "screenshot-shaped."),
        ))
    char_stub = slugify(display_name).split("-")[0][:8].capitalize() or "Mascot"
    char_name = char_stub + ("o" if not char_stub.endswith(("o", "y", "ie")) else "")
    concept = CharacterConceptWire(
        name=char_name,
        role="mascot" if k == "entertainment" else "ambassador",
        persona=(f"{char_name} is obsessed with {kw[0]} and cannot stop starting over — "
                 f"its flaw: it restarts every {kw[1]} project at step one, forever, which "
                 "generates infinite episodes. Deadpan with cracks of hope. Recurring "
                 "off-screen antagonist: THE ALGORITHM, never seen, only felt at 2:47 AM. "
                 "Knows it is AI-generated and jokes about it when natural."),
        visual_desc=(f"A small, deliberately synthetic soft-3D creature themed around "
                     f"{kw[0]}, tired oval eyes, stubby arms. Signature visual anchor prop: "
                     f"a crumpled checklist labeled 'STEP 1 (again)'. Never photorealistic."),
        catchphrases=["step one. again.", "the algorithm said no.", f"day ___ of {kw[0]}."],
    )
    return CampaignPlanWire(
        id_slug=slugify(name or " ".join(desc.split()[:3])),
        name=display_name,
        kind=k,
        description=_first_sentence(desc) + (
            f" Built for people deep in the {kw[0]} trenches." if k == "product"
            else f" An account that exists purely to entertain the {kw[0]} crowd."),
        target_audience=(f"People living the {kw[0]} life — mostly 18-30, extremely online, "
                         f"hanging out on TikTok and X, in subreddits about {kw[1]}. They "
                         f"feel behind, laugh darkly about {kw[2]}, and share anything that "
                         "makes them feel seen."),
        brand_voice=("Casual, specific, slightly irreverent. Short sentences. Punchy hooks. "
                     "Never corporate-speak; speaks like someone who actually lives this."),
        content_rating="standard",
        platforms=plats,
        posting_cadence=[CadenceItem(platform=p, per_day=1) for p in plats],
        specificity_bank=bank,
        pain_veins=pains,
        take_pool=takes,
        trend_subreddits=[slugify(w).replace("-", "") for w in keywords[:4]] or ["niche"],
        trend_keywords=keywords[:3] or ["niche"],
        strategy_briefs=briefs,
        character_concept=concept,
    )


# --------------------------------------------------------------------------- #
# The pipeline
# --------------------------------------------------------------------------- #
def onboard_campaign(app: App, llm: LLM, description: str, *,
                     name: Optional[str] = None, kind: Optional[str] = None,
                     website_url: Optional[str] = None,
                     platforms: Optional[list[str]] = None) -> dict:
    """Research + generate + apply a full campaign config from a description.

    Returns ``{"product": ..., "character": ..., "yaml_path": ..., "plan": ...,
    "briefs_adapted": N, "summary": ...}``.
    """
    user = f"CAMPAIGN DESCRIPTION:\n{description.strip()}\n"
    if name:
        user += f"\nCampaign name (use exactly): {name}"
    if kind:
        user += f"\nCampaign kind (use exactly): {kind}"
    if platforms:
        user += f"\nPlatforms (use exactly): {', '.join(platforms)}"
    if website_url:
        user += f"\nWebsite: {website_url}"

    plan = llm.parse(
        _system_prompt(), user, CampaignPlanWire,
        model=app.settings.llm.text_model,
        temperature=0.8,
        mock_factory=lambda: _mock_plan(description, name, kind, platforms),
    )
    plan = _normalize(plan, description, name=name, kind=kind, platforms=platforms)
    return _apply(app, plan, website_url=website_url)


def _normalize(plan: CampaignPlanWire, description: str, *, name: Optional[str],
               kind: Optional[str], platforms: Optional[list[str]]) -> CampaignPlanWire:
    """Enforce caller overrides + valid values regardless of what the LLM returned."""
    if name:
        plan.name = name
    plan.name = plan.name.strip() or "Campaign"
    plan.id_slug = slugify(plan.id_slug or plan.name)
    plan.kind = (kind or plan.kind or "").strip().lower()
    if plan.kind not in ("product", "entertainment"):
        plan.kind = _infer_kind(description)
    if plan.content_rating not in CONTENT_RATINGS:
        plan.content_rating = "standard"
    wanted = platforms or plan.platforms or ["tiktok", "x"]
    plan.platforms = [p for p in dict.fromkeys(pl.strip().lower() for pl in wanted)
                      if p in KNOWN_PLATFORMS] or ["tiktok", "x"]
    cadence = {c.platform.strip().lower(): max(int(c.per_day or 1), 1)
               for c in plan.posting_cadence}
    plan.posting_cadence = [CadenceItem(platform=p, per_day=cadence.get(p, 1))
                            for p in plan.platforms]
    # Only real strategy ids; requires_product strategies never get briefs for
    # entertainment campaigns (there is no product to demo).
    valid = {s.id: s for s in strategies_mod.STRATEGIES}
    briefs, seen = [], set()
    for b in plan.strategy_briefs:
        s = valid.get(b.strategy_id)
        if s is None or b.strategy_id in seen:
            continue
        if plan.kind == "entertainment" and s.requires_product:
            continue
        seen.add(b.strategy_id)
        briefs.append(b)
    plan.strategy_briefs = briefs
    return plan


def _apply(app: App, plan: CampaignPlanWire, website_url: Optional[str]) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    pid = plan.id_slug
    knowledge = {
        "pain_veins": plan.pain_veins,
        "fact_base": [],  # HARD RULE: human-verified only — onboarding never fills this.
        "take_pool": plan.take_pool,
    }
    cadence = {c.platform: c.per_day for c in plan.posting_cadence}
    catalog = {
        b.strategy_id: {
            "strategist_brief": b.strategist_brief,
            "writer_brief": b.writer_brief,
            "media_brief": b.media_brief,
            "example_sketches": [b.example_sketch] if b.example_sketch.strip() else [],
        }
        for b in plan.strategy_briefs
    }
    trend_sources = {"subreddits": plan.trend_subreddits, "keywords": plan.trend_keywords}

    # 1. Product row: core fields via the ProductConfig upsert, extended columns
    #    (kind, rating, radar, catalog) via update_product.
    cfg = ProductConfig(
        id=pid, name=plan.name, description=plan.description,
        target_audience=plan.target_audience, brand_voice=plan.brand_voice,
        website_url=website_url, platforms=plan.platforms, posting_cadence=cadence,
        specificity_bank=plan.specificity_bank, knowledge=knowledge,
    )
    store.upsert_product(app.conn, cfg, active=True)
    store.update_product(
        app.conn, pid,
        kind=plan.kind, content_rating=plan.content_rating,
        trend_sources=trend_sources, strategy_catalog=catalog,
        specificity_bank=plan.specificity_bank, knowledge=knowledge,
    )

    # 2. Character (lore_state initialized, following the config/characters/*.yaml
    #    bible conventions).
    character = characters_mod.create_from_concept(
        app, pid, plan.character_concept.model_dump())

    # 3. YAML snapshot — the campaign stays inspectable and hand-editable.
    yaml_path = _write_snapshot(app, plan, pid, website_url, cadence, knowledge,
                                trend_sources, catalog, created_at=now)

    db_module.log_activity(
        app.conn, "onboard",
        f"Onboarded campaign “{pid}” ({plan.kind}): {len(plan.platforms)} platform(s), "
        f"{len(plan.strategy_briefs)} strategy brief(s), character “{character['name']}”",
        product_id=pid, level="success")

    product = store.get_product(app.conn, pid)
    return {
        "product": product,
        "character": character,
        "yaml_path": str(yaml_path),
        "plan": plan.model_dump(),
        "briefs_adapted": len(plan.strategy_briefs),
        "summary": {
            "id": pid, "kind": plan.kind, "content_rating": plan.content_rating,
            "platforms": plan.platforms, "character": character["name"],
            "briefs_adapted": len(plan.strategy_briefs),
            "specificity_bank": len(plan.specificity_bank),
            "pain_veins": len(plan.pain_veins), "take_pool": len(plan.take_pool),
        },
    }


def _write_snapshot(app: App, plan: CampaignPlanWire, pid: str,
                    website_url: Optional[str], cadence: dict, knowledge: dict,
                    trend_sources: dict, catalog: dict, created_at: str):
    import yaml

    snapshot = {
        "id": pid,
        "name": plan.name,
        "kind": plan.kind,
        "description": plan.description,
        "target_audience": plan.target_audience,
        "brand_voice": plan.brand_voice,
        "website_url": website_url,
        "content_rating": plan.content_rating,
        "platforms": plan.platforms,
        "posting_cadence": cadence,
        "specificity_bank": plan.specificity_bank,
        "knowledge": knowledge,
        "trend_sources": trend_sources,
        "strategy_catalog": catalog,
        "character": plan.character_concept.model_dump(),
        "_onboarded_at": created_at,
    }
    path = app.paths.products_dir / f"{pid}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(snapshot, sort_keys=False, allow_unicode=True))
    return path
