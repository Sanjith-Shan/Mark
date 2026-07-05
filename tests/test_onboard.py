"""Tests for the campaign onboarding pipeline (src/mark/onboard.py) — all
offline/mock mode: the deterministic mock plan must produce a complete,
applied campaign."""

from __future__ import annotations

import yaml

from mark import characters, db as db_module, onboard, store, strategies

REQUIRES_PRODUCT_IDS = {s.id for s in strategies.STRATEGIES if s.requires_product}

DESCRIPTION = (
    "An AI-powered meal planning app for busy college students who hate "
    "deciding what to cook. It builds a weekly plan from what's already in "
    "the fridge."
)


def test_onboard_creates_full_campaign(app, llm):
    out = onboard.onboard_campaign(app, llm, DESCRIPTION, name="FridgePilot",
                                   website_url="https://fridgepilot.example")
    prod = out["product"]
    pid = prod["id"]
    assert pid == "fridgepilot"
    assert prod["kind"] == "product"
    assert prod["content_rating"] in ("clean", "standard", "edgy")
    assert prod["website_url"] == "https://fridgepilot.example"

    # Trend radar sources are set.
    sources = db_module.loads(prod["trend_sources"], {})
    assert sources.get("subreddits") and sources.get("keywords")

    # Strategy catalog: domain-adapted briefs for every base strategy that fits.
    catalog = db_module.loads(prod["strategy_catalog"], {})
    assert catalog, "no strategy briefs adapted"
    valid_ids = {s.id for s in strategies.STRATEGIES}
    for sid, brief in catalog.items():
        assert sid in valid_ids
        assert brief["strategist_brief"]
        assert brief["writer_brief"]
    assert out["briefs_adapted"] == len(catalog)
    # The adapted briefs actually apply through the campaign catalog.
    adapted = {s.id: s for s in strategies.catalog_for(prod)}
    some_id = next(iter(catalog))
    assert adapted[some_id].strategist_brief == catalog[some_id]["strategist_brief"]

    # Knowledge pools: pains + takes filled, fact_base ALWAYS empty (hard rule).
    knowledge = db_module.loads(prod["knowledge"], {})
    assert knowledge["pain_veins"]
    assert knowledge["take_pool"]
    assert knowledge["fact_base"] == []
    assert db_module.loads(prod["specificity_bank"], [])

    # A character was created with lore_state initialized.
    chars = characters.list_for_product(app, pid)
    assert len(chars) == 1
    c = chars[0]
    assert c["name"] == out["character"]["name"]
    assert c["persona"] and c["visual_desc"]
    assert c["lore_state"].get("episodes_posted") == 0

    # YAML snapshot written and parseable.
    path = app.paths.products_dir / f"{pid}.yaml"
    assert path.exists()
    snap = yaml.safe_load(path.read_text())
    assert snap["id"] == pid
    assert snap["kind"] == "product"
    assert snap["knowledge"]["fact_base"] == []
    assert snap["strategy_catalog"]
    assert snap["character"]["name"] == c["name"]

    # Onboarded campaign is active (multi-campaign model: others keep running).
    assert prod["active"] == 1


def test_entertainment_kind_excludes_requires_product_strategies(app, llm):
    out = onboard.onboard_campaign(
        app, llm,
        "A comedy account of absurdist sketches about houseplants with feelings.",
        name="Blob Theater", kind="entertainment", platforms=["tiktok", "x"])
    prod = out["product"]
    assert prod["kind"] == "entertainment"
    catalog = db_module.loads(prod["strategy_catalog"], {})
    assert catalog
    assert not (set(catalog) & REQUIRES_PRODUCT_IDS), \
        "entertainment campaigns must not get briefs for product-requiring strategies"
    # fact_base stays empty here too.
    assert db_module.loads(prod["knowledge"], {})["fact_base"] == []
    # Platform override honored.
    assert db_module.loads(prod["platforms"], []) == ["tiktok", "x"]


def test_onboard_normalizes_bad_values(app, llm):
    out = onboard.onboard_campaign(app, llm, DESCRIPTION, name="Fridge Pilot 2",
                                   platforms=["tiktok", "myspace", "x"])
    prod = out["product"]
    assert prod["id"] == "fridge-pilot-2"
    # Unknown platforms filtered out; cadence covers exactly the kept platforms.
    plats = db_module.loads(prod["platforms"], [])
    assert plats == ["tiktok", "x"]
    cadence = db_module.loads(prod["posting_cadence"], {})
    assert set(cadence) == {"tiktok", "x"}
    assert all(v >= 1 for v in cadence.values())
