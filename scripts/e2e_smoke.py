"""End-to-end UI smoke test: drives the real app in a browser like a user.

Journey: fresh home → create a campaign in the modal → generate content →
draft appears in Studio → open drawer → edit caption → approve → post now →
content shows as posted. Fails loudly on any broken step.

Usage: python3 scripts/e2e_smoke.py [home_dir]
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PORT = 8412


def wait_port(port: int, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.25)
    raise TimeoutError(f"server on :{port} never came up")


def main(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    if (home / "config").exists():
        shutil.rmtree(home / "config")
    shutil.copytree(REPO / "config", home / "config")

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
        from playwright.sync_api import expect, sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            base = f"http://127.0.0.1:{PORT}"

            # 1. Create a campaign through the modal.
            page.goto(f"{base}/campaigns", wait_until="load")
            page.get_by_role("button", name="New campaign").first.click()
            modal = page.locator(".modal")
            modal.get_by_placeholder("SudoApply").fill("SmokeCo")
            modal.get_by_placeholder("What the product does, key features, why it exists…") \
                .fill("A test product that automates smoke tests for busy engineers.")
            modal.get_by_placeholder("Who you're trying to reach, their pain points, where they hang out…") \
                .fill("Engineers who ship fast and test everything.")
            modal.get_by_placeholder("Tone and style: casual? irreverent? educational? First or second person?") \
                .fill("Dry, precise, a little smug.")
            modal.locator(".checkbox-row", has_text="X").first.click()
            modal.get_by_role("button", name="Create campaign").click()
            expect(page.locator(".card", has_text="SmokeCo").first).to_be_visible(timeout=5000)
            print("✓ campaign created via modal")

            # 2. Generate content from the Studio.
            page.goto(f"{base}/studio", wait_until="load")
            page.get_by_role("button", name="Generate").first.click()
            page.locator(".modal").get_by_role("button", name="Generate").click()
            # Wait for the draft card to appear (job runs in background).
            expect(page.locator(".content-card").first).to_be_visible(timeout=60000)
            print("✓ draft generated and visible in Studio")

            # 3. Open the drawer, edit the caption, save.
            page.locator(".content-card").first.click()
            page.wait_for_timeout(800)
            caption_box = page.locator(".drawer textarea").first
            caption_box.fill("Edited by the smoke test — ship it.")
            page.get_by_role("button", name="Save edits").click()
            page.wait_for_timeout(600)
            print("✓ caption edited and saved")

            # 4. Approve.
            page.locator(".drawer").get_by_role("button", name="Approve").click()
            expect(page.locator(".drawer .pill.approved").first).to_be_visible(timeout=5000)
            print("✓ approved")

            # 5. Post now.
            page.locator(".drawer").get_by_role("button", name="Post now").click()
            expect(page.locator(".drawer .pill.posted").first).to_be_visible(timeout=30000)
            print("✓ posted (mock)")

            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
    print("e2e smoke: ALL PASS")


if __name__ == "__main__":
    home = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="mark-e2e-"))
    main(home)
