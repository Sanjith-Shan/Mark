"""Application context — the single object passed around the codebase.

Holds the resolved settings, on-disk paths, provider credentials, and an open DB
connection. Also centralizes the rule for whether a given provider should use its
real API or its offline/mock path.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from . import db as db_module
from .config import Keys, Paths, Settings, load_dotenv, load_settings


class App:
    """Runtime context. Build one with :func:`get_app` near the program edge."""

    def __init__(
        self,
        paths: Paths,
        settings: Settings,
        keys: Keys,
        conn: sqlite3.Connection,
        force_mock: bool = False,
    ):
        self.paths = paths
        self.settings = settings
        self.keys = keys
        self.conn = conn
        # Global override: env MARK_MOCK or an explicit --dry-run flag.
        import os

        self.force_mock = force_mock or os.environ.get("MARK_MOCK", "").strip() in {"1", "true", "yes"}

    # -- provider availability -------------------------------------------- #
    def is_mock(self, provider: str) -> bool:
        """Return True if ``provider`` must use its offline/mock path."""
        if self.force_mock:
            return True
        key = {
            "openai": self.keys.openai,
            "fal": self.keys.fal,
            "upload_post": self.keys.upload_post,
            "elevenlabs": self.keys.elevenlabs,
        }.get(provider, None)
        return key is None

    @property
    def fully_live(self) -> bool:
        return not any(self.is_mock(p) for p in ("openai", "fal", "upload_post"))

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


def get_app(home: Optional[Path] = None, force_mock: bool = False, ensure_dirs: bool = True) -> App:
    """Construct the application context.

    Loads ``.env``, resolves paths, parses ``default.yaml``, opens (and migrates)
    the database, and snapshots provider credentials.
    """
    paths = Paths(home)
    if ensure_dirs:
        paths.ensure()
    load_dotenv(paths.home)
    settings = load_settings(paths)
    keys = Keys()
    conn = db_module.connect(paths.db_path)
    db_module.init_db(conn)
    return App(paths=paths, settings=settings, keys=keys, conn=conn, force_mock=force_mock)
