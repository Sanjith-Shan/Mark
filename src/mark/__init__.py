"""Mark — a personal autonomous AI marketing engine.

Mark generates platform-specific marketing content for whatever product you're
building, posts it across social platforms, monitors engagement, and uses that
data to improve future content over time.

Design principle: every external provider degrades gracefully. If an API key is
missing or an optional library isn't installed, that provider runs in an
offline/mock path that still produces real local artifacts so the whole pipeline
can be exercised end-to-end before you spend a cent.
"""

__version__ = "0.1.0"
