"""Twitch Helix client — discovery for the stream-clips lane.

Read-only Helix with an app access token (client-credentials): who's live
(`get_streams`), the audience-voted top clips per broadcaster in a time window
(`get_clips` — Helix returns them in DESCENDING VIEW ORDER, so "top clips in
the last 2h" is one free call), and login→id resolution (`get_users`).
Downloading the actual clip files is `sourcing.ytdlp`'s job — and only for
broadcasters we have campaign permission for (see the policy note there).

Token: module-level cache; client-credentials tokens live ~60 days, we refresh
early and retry once on 401. Rate limit is a generous point bucket (~800/min) —
polling a small roster every 10-15 min doesn't approach it.

MOCK MODE (``app.force_mock`` or either env key missing): plausible
deterministic fake streams/clips/users so tests and offline pipelines run.

INTEGRATION
-----------
* Env keys (read from ``os.environ``, populated by ``.env``):
  ``TWITCH_CLIENT_ID`` + ``TWITCH_CLIENT_SECRET`` — register an application at
  dev.twitch.tv/console (category: Application Integration), free.
* Suggested config: the stream-clips template should carry a permissioned
  broadcaster roster (login + campaign credit string + submission deadline);
  this module deliberately takes ids/logins as arguments and owns no roster.
* Activity feed: one `log_activity` line per real fetch, never per item.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from .. import db as db_module
from ..app import App

log = logging.getLogger("mark.sourcing.twitch")

_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_HELIX = "https://api.twitch.tv/helix"

# Module-level app-token cache: {"token": str, "expires_at": epoch_seconds}.
_token_cache: dict = {}


def _creds() -> tuple[Optional[str], Optional[str]]:
    return (os.environ.get("TWITCH_CLIENT_ID") or None,
            os.environ.get("TWITCH_CLIENT_SECRET") or None)


def _is_mock(app: App) -> bool:
    cid, secret = _creds()
    return app.force_mock or not (cid and secret)


def _app_token(force_refresh: bool = False) -> str:
    """Client-credentials app token, cached until ~1h before expiry."""
    now = time.time()
    if (not force_refresh and _token_cache.get("token")
            and now < _token_cache.get("expires_at", 0) - 3600):
        return _token_cache["token"]
    import httpx

    cid, secret = _creds()
    with httpx.Client(timeout=15) as client:
        resp = client.post(_TOKEN_URL, data={
            "client_id": cid, "client_secret": secret,
            "grant_type": "client_credentials"})
        resp.raise_for_status()
        data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + float(data.get("expires_in") or 3600)
    return _token_cache["token"]


def _helix_get(path: str, params: list[tuple[str, str]]) -> dict:
    """GET a Helix endpoint; one automatic token refresh + retry on 401."""
    import httpx

    cid, _ = _creds()
    for attempt in (0, 1):
        token = _app_token(force_refresh=attempt > 0)
        with httpx.Client(timeout=20) as client:
            resp = client.get(f"{_HELIX}/{path}", params=params,
                              headers={"Client-Id": cid or "",
                                       "Authorization": f"Bearer {token}"})
        if resp.status_code == 401 and attempt == 0:
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("twitch helix auth failed after token refresh")


# --------------------------------------------------------------------------- #
# Streams
# --------------------------------------------------------------------------- #
def get_streams(app: App, *, logins: Optional[list[str]] = None,
                game_id: Optional[str] = None, first: int = 20) -> list[dict]:
    """Live streams, biggest first. Filter by ``logins`` and/or ``game_id``.
    Normalized: id, user_id, user_login, user_name, game_id, game_name, title,
    viewer_count, started_at, language, thumbnail_url."""
    if _is_mock(app):
        return _mock_streams(logins, game_id, first)
    params: list[tuple[str, str]] = [("first", str(min(max(first, 1), 100)))]
    for login in logins or []:
        params.append(("user_login", login))
    if game_id:
        params.append(("game_id", game_id))
    try:
        data = _helix_get("streams", params)
    except Exception as exc:
        log.warning("twitch get_streams failed: %s", exc)
        return []
    items = [{
        "id": s.get("id"),
        "user_id": s.get("user_id"),
        "user_login": s.get("user_login"),
        "user_name": s.get("user_name"),
        "game_id": s.get("game_id"),
        "game_name": s.get("game_name"),
        "title": s.get("title"),
        "viewer_count": int(s.get("viewer_count") or 0),
        "started_at": s.get("started_at"),
        "language": s.get("language"),
        "thumbnail_url": s.get("thumbnail_url"),
    } for s in data.get("data") or []]
    db_module.log_activity(
        app.conn, "sourcing",
        f"Twitch streams refresh → {len(items)} live"
        + (f" ({', '.join((logins or [])[:4])}…)" if logins and len(logins) > 4
           else (f" ({', '.join(logins)})" if logins else "")))
    return items


# --------------------------------------------------------------------------- #
# Clips
# --------------------------------------------------------------------------- #
def get_clips(app: App, broadcaster_id: str, *, started_at: Optional[str] = None,
              first: int = 20, after: Optional[str] = None,
              ) -> tuple[list[dict], Optional[str]]:
    """Top clips for a broadcaster (Helix returns descending view order), so a
    recent ``started_at`` window (RFC3339 UTC; ended_at defaults to +1 week)
    IS the moment detector — the audience already voted by clipping.

    Returns ``(items, cursor)``; pass ``after=cursor`` for the next page.
    Normalized: id, url, broadcaster_id, broadcaster_name, creator_name,
    video_id, game_id, title, view_count, created_at, duration, vod_offset,
    thumbnail_url."""
    if _is_mock(app):
        return _mock_clips(broadcaster_id, first, after)
    params: list[tuple[str, str]] = [
        ("broadcaster_id", broadcaster_id),
        ("first", str(min(max(first, 1), 100))),
    ]
    if started_at:
        params.append(("started_at", started_at))
    if after:
        params.append(("after", after))
    try:
        data = _helix_get("clips", params)
    except Exception as exc:
        log.warning("twitch get_clips failed for %s: %s", broadcaster_id, exc)
        return [], None
    items = [{
        "id": c.get("id"),
        "url": c.get("url"),
        "broadcaster_id": c.get("broadcaster_id"),
        "broadcaster_name": c.get("broadcaster_name"),
        "creator_name": c.get("creator_name"),
        "video_id": c.get("video_id"),
        "game_id": c.get("game_id"),
        "title": c.get("title"),
        "view_count": int(c.get("view_count") or 0),
        "created_at": c.get("created_at"),
        "duration": float(c.get("duration") or 0),
        "vod_offset": c.get("vod_offset"),
        "thumbnail_url": c.get("thumbnail_url"),
    } for c in data.get("data") or []]
    cursor = (data.get("pagination") or {}).get("cursor") or None
    if not after:  # log once per refresh, not per page
        db_module.log_activity(
            app.conn, "sourcing",
            f"Twitch clips refresh for {broadcaster_id} → {len(items)} clips"
            + (f" since {started_at}" if started_at else ""))
    return items, cursor


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
def get_users(app: App, logins: list[str]) -> list[dict]:
    """Resolve logins → user records (id needed for get_clips). Normalized:
    id, login, display_name, description, profile_image_url, created_at."""
    if not logins:
        return []
    if _is_mock(app):
        return _mock_users(logins)
    params = [("login", login) for login in logins[:100]]
    try:
        data = _helix_get("users", params)
    except Exception as exc:
        log.warning("twitch get_users failed: %s", exc)
        return []
    return [{
        "id": u.get("id"),
        "login": u.get("login"),
        "display_name": u.get("display_name"),
        "description": u.get("description"),
        "profile_image_url": u.get("profile_image_url"),
        "created_at": u.get("created_at"),
    } for u in data.get("data") or []]


# --------------------------------------------------------------------------- #
# Offline mocks — plausible, deterministic
# --------------------------------------------------------------------------- #
_MOCK_ROSTER = [
    ("41001", "mockstreamer", "MockStreamer", "Just Chatting", "509658", 18432),
    ("41002", "pixelqueen", "PixelQueen", "VALORANT", "516575", 9210),
    ("41003", "grindcaster", "GrindCaster", "Minecraft", "27471", 3105),
]


def _mock_streams(logins, game_id, first) -> list[dict]:
    roster = _MOCK_ROSTER
    if logins:
        roster = [r for r in roster if r[1] in set(logins)] or roster[:1]
    if game_id:
        roster = [r for r in roster if r[4] == game_id] or roster[:1]
    return [{
        "id": f"stream-{uid}", "user_id": uid, "user_login": login,
        "user_name": name, "game_id": gid, "game_name": game,
        "title": f"{name} goes live (mock)", "viewer_count": viewers,
        "started_at": "2026-07-06T17:00:00Z", "language": "en",
        "thumbnail_url": f"https://example.com/{login}-{{width}}x{{height}}.jpg",
    } for uid, login, name, game, gid, viewers in roster[:first]]


def _mock_clips(broadcaster_id, first, after) -> tuple[list[dict], Optional[str]]:
    if after:  # one mock page is enough — cursor round-trips to the end
        return [], None
    titles = ["insane clutch", "chat broke him", "unexpected duet",
              "the 1hp escape", "lobby speechless"]
    items = [{
        "id": f"MockClip-{broadcaster_id}-{i}",
        "url": f"https://clips.twitch.tv/MockClip-{broadcaster_id}-{i}",
        "broadcaster_id": broadcaster_id,
        "broadcaster_name": "MockStreamer",
        "creator_name": f"viewer{i}",
        "video_id": f"v{broadcaster_id}00{i}",
        "game_id": "509658",
        "title": titles[i % len(titles)],
        "view_count": 5000 - i * 900,       # descending view order, like Helix
        "created_at": "2026-07-06T16:30:00Z",
        "duration": 26.0 + i * 3,
        "vod_offset": 3600 + i * 250,
        "thumbnail_url": f"https://example.com/clip-{i}.jpg",
    } for i in range(min(first, 5))]
    return items, "mock-cursor-end"


def _mock_users(logins) -> list[dict]:
    known = {login: (uid, name) for uid, login, name, *_ in _MOCK_ROSTER}
    out = []
    for i, login in enumerate(logins):
        uid, name = known.get(login, (f"49{i:03d}", login.capitalize()))
        out.append({
            "id": uid, "login": login, "display_name": name,
            "description": f"{name} — mock twitch user",
            "profile_image_url": f"https://example.com/{login}.png",
            "created_at": "2020-01-01T00:00:00Z",
        })
    return out
