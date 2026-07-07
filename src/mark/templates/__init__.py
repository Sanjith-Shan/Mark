"""Template registry — self-contained content-template modules.

Each template module (see docs/design/CONTENT-TEMPLATES-BUILD.md, Contract 5)
exposes a ``STRATEGY`` (or ``STRATEGIES``) plus a ``produce(...)`` function with
the same signature/return shape as :func:`mark.media.video.produce_video`, and
optionally ``refresh(app, llm)`` for discovery-driven templates.

This package aggregates them into:

- ``PRODUCERS``: strategy_id -> produce function (dispatched from
  ``mark.agents.media.produce_media``)
- ``DISCOVERY``: strategy_id -> refresh function (run from the scheduler's
  fast-trends pulse alongside the humor radar)

and registers all template strategies into the main catalog via
:func:`mark.strategies.register`. Import failures in individual template
modules are tolerated (a template with a missing optional dep must never take
down the whole pipeline) — they are logged and skipped.
"""

from __future__ import annotations

import importlib
import logging

log = logging.getLogger(__name__)

# Template modules, in registration order. Each is optional at runtime.
_MODULES = [
    "motivational",
    "animal_story",
    "recap",
    "ambassador",
    "livestream",
    "campaigns",
]

PRODUCERS: dict = {}
DISCOVERY: dict = {}
_loaded = False


def ensure_loaded() -> None:
    """Import all template modules once, registering their strategies."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    from .. import strategies as strategies_mod

    for name in _MODULES:
        try:
            mod = importlib.import_module(f".{name}", __package__)
        except Exception as exc:  # missing module/dep — skip, never crash
            log.debug("template module %s not loaded: %s", name, exc)
            continue
        strats = getattr(mod, "STRATEGIES", None) or (
            [mod.STRATEGY] if getattr(mod, "STRATEGY", None) else [])
        if strats:
            strategies_mod.register(list(strats))
        produce = getattr(mod, "produce", None)
        refresh = getattr(mod, "refresh", None)
        for s in strats:
            if produce:
                PRODUCERS[s.id] = produce
            if refresh:
                DISCOVERY[s.id] = refresh
