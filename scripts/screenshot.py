"""Visual harness: boot the web app against a seeded demo home and screenshot
every page (plus key interactions) so design can be reviewed and iterated.

Usage:
    python3 scripts/demo_seed.py /tmp/mark-demo          # once
    python3 scripts/screenshot.py /tmp/mark-demo out/    # every iteration
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PAGES = [
    ("dashboard", "/"),
    ("campaigns", "/campaigns"),
    ("studio", "/studio"),
    ("analytics", "/analytics"),
    ("trends", "/trends"),
    ("learn", "/learn"),
    ("autopilot", "/autopilot"),
    ("settings", "/settings"),
]


def wait_port(port: int, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.25)
    raise TimeoutError(f"server on :{port} never came up")


def main(home: str, out_dir: str, port: int = 8399) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, "MARK_MOCK": "1", "PYTHONPATH": str(REPO / "src")}
    server = subprocess.Popen(
        [sys.executable, "-c",
         f"from mark.web.server import serve; from pathlib import Path; "
         f"serve(home=Path({home!r}), port={port}, force_mock=True)"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    try:
        wait_port(port)
        time.sleep(0.8)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900},
                                    device_scale_factor=2)
            base = f"http://127.0.0.1:{port}"
            for name, path in PAGES:
                page.goto(base + path, wait_until="load")
                page.wait_for_timeout(700)
                page.screenshot(path=str(out / f"{name}.png"))
                print(f"✓ {name}")

            # Interactions: studio drawer + campaign modal.
            page.goto(base + "/studio", wait_until="load")
            page.wait_for_timeout(600)
            cards = page.locator(".content-card")
            if cards.count() > 0:
                cards.first.click()
                page.wait_for_timeout(900)
                page.screenshot(path=str(out / "studio-drawer.png"))
                print("✓ studio-drawer")
                page.keyboard.press("Escape")

            page.goto(base + "/campaigns", wait_until="load")
            page.wait_for_timeout(500)
            btn = page.get_by_role("button", name="New campaign")
            if btn.count() > 0:
                btn.first.click()
                page.wait_for_timeout(500)
                page.screenshot(path=str(out / "campaign-modal.png"))
                print("✓ campaign-modal")

            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()  # open SSE connections can stall graceful shutdown
            server.wait(timeout=5)
    print(f"screenshots → {out}")


if __name__ == "__main__":
    home = sys.argv[1] if len(sys.argv) > 1 else "/tmp/mark-demo"
    out = sys.argv[2] if len(sys.argv) > 2 else "screenshots"
    main(home, out)
