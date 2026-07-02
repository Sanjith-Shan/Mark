"""FastAPI app factory + `mark web` entry point.

Serves the REST API under /api, generated media under /media, and the built
React frontend (src/mark/web/static) for everything else, with an SPA fallback
so client-side routes deep-link correctly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import build_router
from .runtime import Runtime

STATIC_DIR = Path(__file__).parent / "static"


def create_app(home: Optional[Path] = None, force_mock: bool = False) -> FastAPI:
    rt = Runtime(home=home, force_mock=force_mock)
    app = FastAPI(title="Mark", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.runtime = rt

    app.include_router(build_router(rt))

    # Generated media (images/videos) straight off disk.
    media_dir = rt.app().paths.media_dir
    media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")

    # Built frontend + SPA fallback.
    if STATIC_DIR.exists():
        assets = STATIC_DIR / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            candidate = (STATIC_DIR / path).resolve()
            if (path and candidate.is_file()
                    and str(candidate).startswith(str(STATIC_DIR.resolve()))):
                return FileResponse(candidate)
            index = STATIC_DIR / "index.html"
            if index.exists():
                return FileResponse(index)
            return JSONResponse({"error": "frontend not built — run `npm run build` in web/"},
                                status_code=503)

    @app.on_event("shutdown")
    def _shutdown() -> None:
        rt.shutdown()

    return app


def serve(home: Optional[Path] = None, host: str = "127.0.0.1", port: int = 8321,
          force_mock: bool = False, autopilot: bool = False) -> None:
    """Run the web app (called by `mark web`)."""
    import uvicorn

    app = create_app(home=home, force_mock=force_mock)
    if autopilot:
        app.state.runtime.autopilot.start()
    uvicorn.run(app, host=host, port=port, log_level="info")
