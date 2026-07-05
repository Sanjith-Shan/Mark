"""upload-post.com client — one API for posting across all social platforms.

Real path uses upload-post.com's REST API over httpx (no hard dependency on their
SDK). Offline path returns deterministic synthetic responses so the posting flow
can be exercised end-to-end without an account.

Every method returns a normalized dict::

    {"request_id": str, "results": {platform: {"post_id": str|None, "status": str}}}
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from ..app import App
from ..llm import _retry, log_external_cost

BASE_URL = "https://api.upload-post.com/api"

# Map Mark's platform names to upload-post's, if they ever diverge.
PLATFORM_MAP = {"x": "x"}


def _ext_platform(p: str) -> str:
    return PLATFORM_MAP.get(p, p)


class UploadPostClient:
    def __init__(self, app: App, profile: Optional[str] = None):
        self.app = app
        self.key = app.keys.upload_post
        # Per-campaign profile override (multi-account test lab): each campaign
        # can post through its own upload-post profile / connected accounts.
        self.user = profile or app.settings.upload_post.profile_username

    @property
    def mock(self) -> bool:
        return self.app.is_mock("upload_post")

    # -- public API ------------------------------------------------------- #
    def upload_video(self, video_path: str, title: str, platforms: list[str],
                     *, first_comment: Optional[str] = None, **extra) -> dict:
        if self.mock:
            return self._mock_response(platforms, kind="video")
        data = {"title": title, "user": self.user}
        if first_comment:
            data["first_comment"] = first_comment
        if "tiktok" in platforms:
            # Docs name the param privacy_level; older SDK used tiktokPrivacyLevel.
            # Send both — unknown form fields are ignored server-side.
            level = extra.get("tiktok_privacy", self.app.settings.platform("tiktok").privacy_level
                              or "PUBLIC_TO_EVERYONE")
            data["privacy_level"] = level
            data["tiktokPrivacyLevel"] = level
        data.update(_platform_params(platforms, extra))
        return self._post("/upload", data, platforms,
                          file_specs={"video": video_path})

    def upload_photo(self, photo_paths: list[str], title: str, platforms: list[str],
                     *, first_comment: Optional[str] = None, **extra) -> dict:
        if self.mock:
            return self._mock_response(platforms, kind="photo")
        data = {"title": title, "user": self.user}
        if first_comment:
            data["first_comment"] = first_comment
        data.update(_platform_params(platforms, extra))
        return self._post("/upload_photos", data, platforms,
                          file_specs=[("photos[]", p) for p in photo_paths])

    def upload_text(self, text: str, platforms: list[str],
                    *, first_comment: Optional[str] = None, **extra) -> dict:
        if self.mock:
            return self._mock_response(platforms, kind="text")
        data = {"title": text, "user": self.user}
        if first_comment:
            data["first_comment"] = first_comment
        data.update(_platform_params(platforms, extra))
        return self._post("/upload_text", data, platforms)

    def post_analytics(self, request_id: str) -> dict:
        if self.mock:
            return {"request_id": request_id, "mock": True}
        return self._get(f"/uploadposts/post-analytics/{request_id}")

    def total_impressions(self) -> dict:
        if self.mock:
            return {"profile": self.user, "mock": True}
        return self._get(f"/uploadposts/total-impressions/{self.user}")

    def get_comments(self, platform: str, post_id: str, limit: int = 50) -> list[dict]:
        """Fetch comments for a post. upload-post only documents this for
        Instagram; other platforms return []. Normalized: {text, author, ts}."""
        if self.mock or platform != "instagram" or not post_id:
            return []
        try:
            raw = self._get(f"/uploadposts/comments?platform=instagram"
                            f"&user={self.user}&post_id={post_id}&limit={min(limit, 50)}")
        except Exception:
            return []
        out = []
        for c in raw.get("comments", []) or []:
            if isinstance(c, dict) and c.get("text"):
                out.append({"text": c["text"],
                            "author": (c.get("user") or {}).get("username"),
                            "ts": c.get("timestamp")})
        return out

    def profile_info(self) -> dict:
        """Connected social accounts for the configured profile (Settings page)."""
        if self.mock:
            return {"username": self.user, "mock": True, "social_accounts": {}}
        try:
            return self._get(f"/uploadposts/users/{self.user}")
        except Exception as exc:  # surface as data, not a crash
            return {"username": self.user, "error": str(exc), "social_accounts": {}}

    # -- transport -------------------------------------------------------- #
    def _headers(self) -> dict:
        return {"Authorization": f"Apikey {self.key}"}

    def _post(self, path: str, data: dict, platforms: list[str],
              file_specs=None) -> dict:
        import httpx

        # upload-post expects repeated platform[] fields; httpx expands a list
        # value into repeated fields (a list-of-tuples `data` would be treated
        # as raw content and silently drop `files`).
        form = {**data, "platform[]": [_ext_platform(p) for p in platforms]}

        def _call():
            # Files are (re)opened per attempt: reusing handles across retries
            # sends exhausted streams — a transient error would turn into a
            # zero-byte upload (or a duplicate post with empty media).
            files = _open_files(file_specs)
            try:
                with httpx.Client(timeout=120) as client:
                    resp = client.post(BASE_URL + path, headers=self._headers(),
                                       data=form, files=files)
                    resp.raise_for_status()
                    return resp.json()
            finally:
                _close_files(files)

        raw = _retry(_call)
        log_external_cost(self.app, "upload_post", "post", path, units=len(platforms))
        return _normalize(raw, platforms)

    def _get(self, path: str) -> dict:
        import httpx

        def _call():
            with httpx.Client(timeout=60) as client:
                resp = client.get(BASE_URL + path, headers=self._headers())
                resp.raise_for_status()
                return resp.json()

        return _retry(_call)

    # -- offline ---------------------------------------------------------- #
    def _mock_response(self, platforms: list[str], kind: str) -> dict:
        rid = f"mock-{uuid.uuid4().hex[:12]}"
        log_external_cost(self.app, "upload_post", "post", kind,
                          units=len(platforms), mocked=True)
        return {
            "request_id": rid,
            "results": {p: {"post_id": f"mock_{p}_{uuid.uuid4().hex[:8]}",
                            "status": "success"} for p in platforms},
        }


def _platform_params(platforms: list[str], extra: dict) -> dict:
    """Per-platform required params (from caller-supplied extras).

    Reddit requires a subreddit (and a title, which we always send); Pinterest
    requires a board id. Callers pull these from the product's platform_options.
    """
    out: dict = {}
    if "reddit" in platforms and extra.get("subreddit"):
        out["subreddit"] = str(extra["subreddit"]).removeprefix("r/")
    if "pinterest" in platforms and extra.get("pinterest_board_id"):
        out["pinterest_board_id"] = extra["pinterest_board_id"]
    return out


def _open_files(file_specs):
    """{"field": path} or [(field, path), ...] → httpx files argument."""
    if not file_specs:
        return None
    items = file_specs.items() if isinstance(file_specs, dict) else file_specs
    return [(field, (Path(p).name, open(p, "rb"))) for field, p in items]


def _close_files(files) -> None:
    if not files:
        return
    items = files.items() if isinstance(files, dict) else files
    for _, payload in items:
        try:
            payload[1].close()
        except Exception:
            pass


def _normalize(raw: dict, platforms: list[str]) -> dict:
    """Defensively map upload-post's response into our normalized shape."""
    request_id = (raw.get("request_id") or raw.get("requestId")
                  or raw.get("id") or f"up-{uuid.uuid4().hex[:10]}")
    results = {}
    raw_results = raw.get("results") or raw.get("platforms") or {}
    for p in platforms:
        entry = raw_results.get(p) or raw_results.get(_ext_platform(p)) or {}
        if isinstance(entry, dict):
            post_id = (entry.get("post_id") or entry.get("id")
                       or entry.get("platform_post_id"))
            # upload-post reports per-platform outcome as a `success` boolean
            # (with an `error` string), not a `status` field.
            if "success" in entry:
                status = "success" if entry.get("success") else "failed"
            else:
                status = entry.get("status", "success")
            error = entry.get("error") or entry.get("message")
        else:
            post_id, status, error = None, "success", None
        results[p] = {"post_id": post_id, "status": status, "error": error}
    return {"request_id": str(request_id), "results": results, "raw": raw}
