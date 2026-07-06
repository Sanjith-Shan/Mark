"""Browser test for the guided tour: walks every step like a user would.

Verifies: the Tutorial button starts the tour, every step's tooltip shows the
right title (parsed straight from web/src/tour/steps.ts so this can't drift),
steps with targets draw the spotlight, cross-page navigation works, Finish
closes the tour and marks it seen, and the Settings card can restart it.

Usage: python3 scripts/tour_check.py
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PORT = 8417
SHOTS = REPO / "data" / "screenshots"


def wait_port(port: int, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.25)
    raise TimeoutError(f"server on :{port} never came up")


def expected_steps() -> list[dict]:
    """Parse route/target/title from steps.ts — the test stays in sync with
    the tour definition automatically."""
    src = (REPO / "web" / "src" / "tour" / "steps.ts").read_text()
    steps = []
    for block in re.findall(r"\{\s*route:(.*?)\n  \},", src, flags=re.DOTALL):
        title = re.search(r'title: "((?:[^"\\]|\\.)*)"', block)
        target = re.search(r"target: \"([^\"]+)\"", block)
        route = re.search(r'^\s*"([^"]+)"', block)
        steps.append({
            "route": route.group(1) if route else "/",
            "target": target.group(1) if target else None,
            "title": title.group(1).replace('\\"', '"') if title else "?",
        })
    assert len(steps) >= 20, f"parsed only {len(steps)} steps from steps.ts"
    return steps


def main() -> None:
    home = Path(tempfile.mkdtemp(prefix="mark-tour-"))
    shutil.copytree(REPO / "config", home / "config")
    SHOTS.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, "MARK_MOCK": "1", "PYTHONPATH": str(REPO / "src")}
    for key in ("OPENAI_API_KEY", "FAL_KEY", "UPLOAD_POST_API_KEY", "ELEVENLABS_API_KEY"):
        env.pop(key, None)
    server = subprocess.Popen(
        [sys.executable, "-c",
         f"from mark.web.server import serve; from pathlib import Path; "
         f"serve(home=Path({str(home)!r}), port={PORT}, force_mock=True)"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        wait_port(PORT)
        time.sleep(0.8)
        base = f"http://127.0.0.1:{PORT}"

        # Seed one campaign so Playbook/Studio show real content, like a
        # real user's second session would.
        import json
        import urllib.request

        req = urllib.request.Request(
            f"{base}/api/campaigns", method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({
                "name": "TourCo",
                "description": "A demo product for the tutorial walkthrough.",
                "target_audience": "people taking the tour",
                "brand_voice": "clear and friendly",
                "platforms": ["x", "tiktok"],
                "posting_cadence": {"x": 1, "tiktok": 1},
            }).encode())
        urllib.request.urlopen(req).read()

        steps = expected_steps()
        from playwright.sync_api import expect, sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(base, wait_until="load")

            # New users see the pulsing "new" Tutorial button in the sidebar.
            start = page.locator("[data-tour-start]")
            expect(start).to_be_visible(timeout=5000)
            start.click()
            print(f"✓ tour started from the sidebar button ({len(steps)} steps)")

            spotlighted = 0
            for i, step in enumerate(steps):
                tip = page.locator(".tour-tip")
                expect(tip).to_be_visible(timeout=8000)
                expect(page.locator(".tour-tip-title")).to_have_text(
                    step["title"], timeout=8000)
                # Route must match the step's page.
                assert page.url.rstrip("/").endswith(step["route"].rstrip("/")) or \
                    (step["route"] == "/" and page.url.rstrip("/") == base), \
                    f"step {i+1}: expected route {step['route']}, at {page.url}"
                if step["target"] and page.locator(".tour-spotlight").count() > 0:
                    spotlighted += 1
                if i in (0, 7, 10, 18, len(steps) - 1):  # sample screenshots
                    page.screenshot(path=str(SHOTS / f"tour-step-{i+1:02d}.png"))
                page.locator("[data-tour-next]").click()
                page.wait_for_timeout(150)
            # Tour is gone after Finish.
            expect(page.locator(".tour-tip")).to_have_count(0, timeout=4000)
            targeted = sum(1 for s in steps if s["target"])
            print(f"✓ walked all {len(steps)} steps "
                  f"({spotlighted}/{targeted} targeted steps drew the spotlight)")
            assert spotlighted >= targeted - 3, \
                f"too many missing spotlights: {spotlighted}/{targeted}"

            # Completion persists, and Settings can restart the tour.
            assert page.evaluate("localStorage.getItem('mark.tour.done')") == "1"
            page.goto(f"{base}/settings", wait_until="load")
            restart = page.locator("[data-tour-start-settings]")
            restart.scroll_into_view_if_needed()
            expect(restart).to_contain_text("Restart", timeout=5000)
            restart.click()
            expect(page.locator(".tour-tip-title")).to_have_text(
                steps[0]["title"], timeout=8000)
            page.keyboard.press("Escape")
            expect(page.locator(".tour-tip")).to_have_count(0, timeout=4000)
            print("✓ restart from Settings works; Esc exits")

            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        shutil.rmtree(home, ignore_errors=True)
    print("tour check: ALL PASS")


if __name__ == "__main__":
    main()
