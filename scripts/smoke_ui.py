#!/usr/bin/env python3
"""NetSim-RT UI Smoke Test using Playwright."""
import os
import sys
import time
import socket
import subprocess
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

def run_smoke():
    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        # Wait for server to come up
        ready = False
        for _ in range(30):
            try:
                res = urlopen(f"{base_url}/api/health", timeout=1)
                if res.status == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.2)
        
        if not ready:
            print("FAIL: Server failed to start")
            return 1

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            console_errors = []
            page_errors = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            # Check 1: Initial load
            page.goto(base_url, wait_until="networkidle")
            page.wait_for_timeout(1000)
            if not console_errors and not page_errors:
                print("PASS: Page load (no console or page errors)")
            else:
                print(f"FAIL: Page load errors: console={console_errors}, page={page_errors}")

            # Check 2: Tab navigation (all 8 tabs including Validation)
            tab_ids = [
                "presets-tab", "simulator-tab", "sweep-tab",
                "shootout-tab", "custom-tab", "datasets-tab", "architecture-tab", "validation-tab"
            ]
            tabs_ok = True
            for tid in tab_ids:
                btn = page.locator(f"button[data-tab='{tid}']")
                if not btn.is_visible():
                    tabs_ok = False
                    break
                btn.click()
                page.wait_for_timeout(200)
                sec = page.locator(f"#{tid}")
                if not sec.is_visible():
                    tabs_ok = False
                    break
            print("PASS: Tab navigation (all 8 tabs)" if tabs_ok else "FAIL: Tab navigation")

            # Check 3: Preset cards rendering & inspection
            page.locator("button[data-tab='presets-tab']").click()
            page.wait_for_selector(".preset-card", timeout=5000)
            cards = page.locator(".preset-card")
            card_count = cards.count()
            preset_ok = (card_count == 6)
            
            # Click first preset "Inspect Scenario"
            cards.first.locator(".btn-inspect").click()
            page.wait_for_timeout(1000)
            chart_canvas = page.locator("#preset-chart canvas, #preset-chart svg")
            if chart_canvas.count() > 0 and preset_ok:
                print(f"PASS: Presets list & scenario inspection ({card_count} cards rendered)")
            else:
                print(f"FAIL: Presets inspection (cards={card_count}, chart={chart_canvas.count()})")

            # Check 4: Built-in simulation run
            page.locator("button[data-tab='simulator-tab']").click()
            page.wait_for_timeout(300)
            page.locator("#btn-run-sim").click()
            sim_rendered = False
            for _ in range(25):
                sim_canvas = page.locator("#sim-timeline-chart canvas, #sim-timeline-chart svg")
                if sim_canvas.count() > 0:
                    sim_rendered = True
                    break
                page.wait_for_timeout(300)
            if sim_rendered:
                print("PASS: Built-in simulation run and charts rendering")
            else:
                print("FAIL: Built-in simulation did not render charts")

            # Check 5: Custom policy sandbox run
            page.locator("button[data-tab='custom-tab']").click()
            page.wait_for_timeout(300)
            page.locator("#btn-load-template").click()
            page.wait_for_timeout(300)
            page.locator("#btn-run-custom").click()
            page.wait_for_timeout(3000)
            custom_canvas = page.locator("#custom-comparison-chart canvas, #custom-comparison-chart svg")
            if custom_canvas.count() > 0:
                print("PASS: Sandboxed custom policy execution and chart comparison")
            else:
                print("FAIL: Sandboxed custom policy execution failed")

            # Check 6: Load sweep run
            page.locator("button[data-tab='sweep-tab']").click()
            page.wait_for_timeout(300)
            # Use small sweep for speed or verify preset load
            page.locator("#btn-run-sweep").click()
            # wait up to 10s for sweep
            for _ in range(20):
                sweep_canvas = page.locator("#sweep-latency-chart canvas, #sweep-latency-chart svg")
                if sweep_canvas.count() > 0:
                    break
                page.wait_for_timeout(500)
            if sweep_canvas.count() > 0:
                print("PASS: Load sweep execution and knee curve rendering")
            else:
                print("FAIL: Load sweep did not render chart")

            browser.close()
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            server_proc.kill()

    return 0

if __name__ == "__main__":
    sys.exit(run_smoke())
