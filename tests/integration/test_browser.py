"""Run the checkout-backed Pyodide example in a real Chromium browser."""

import functools
import http.server
import os
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).parents[2]
RESULTS = PROJECT_ROOT / "browser-results"


class PyodideBrowserTests(unittest.TestCase):
    def test_drawing_and_keyboard_callback_with_both_renderer_startup_orders(self):
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(PROJECT_ROOT)
        )
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        RESULTS.mkdir(exist_ok=True)

        with sync_playwright() as playwright:
            options = {}
            if os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"):
                options["executable_path"] = os.environ[
                    "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"
                ]
            browser = playwright.chromium.launch(**options)
            try:
                for delayed in (False, True):
                    with self.subTest(delayed_renderer=delayed):
                        self.check_example(browser, server.server_port, delayed)
            finally:
                browser.close()

    def check_example(self, browser, port, delayed):
        label = "delayed" if delayed else "normal"
        context = browser.new_context()
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.set_default_timeout(120_000)
        errors = []
        held_requests = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        if delayed:
            # Hold the renderer until Python has finished, so commands must
            # survive the iframe startup race before they can be displayed.
            page.route("**/standalone.html?*", lambda route: held_requests.append(route))
        try:
            page.goto(
                f"http://127.0.0.1:{port}/examples/pyodide/",
                wait_until="domcontentloaded",
            )
            page.wait_for_function(
                "['ready', 'error'].includes(document.querySelector('#status').dataset.state)"
            )
            self.assertEqual(
                page.locator("#status").get_attribute("data-state"),
                "ready",
                page.locator("#output").inner_text(),
            )
            print(f"Pyodide ({label}): runtime ready", flush=True)
            page.locator("#code").fill(
                "import turtle\n"
                "from basthon import turtle as candidate\n"
                "assert turtle is candidate\n"
                "turtle.speed(0)\n"
                "turtle.forward(80)\n"
                "turtle.left(90)\n"
                "turtle.forward(40)\n"
                "def move():\n"
                "    turtle.forward(20)\n"
                "    print('callback received')\n"
                "turtle.onkeypress(move, 'space')\n"
                "turtle.listen()\n"
            )
            page.locator("#run").click()
            page.wait_for_function(
                "['finished', 'error'].includes(document.querySelector('#status').dataset.state)"
            )
            self.assertEqual(
                page.locator("#status").get_attribute("data-state"),
                "finished",
                page.locator("#output").inner_text(),
            )
            print(f"Pyodide ({label}): drawing code finished", flush=True)
            if delayed:
                self.assertTrue(held_requests)
                for route in held_requests:
                    route.continue_()
            canvas = page.frame_locator("#canvas")
            canvas.locator("#drawing").wait_for(state="attached")
            frame = page.locator("#canvas").element_handle().content_frame()
            has_endpoint = """([x, y]) =>
                [...document.querySelectorAll('#drawing line')].some(line =>
                    Math.abs(Number(line.getAttribute('x2')) - x) < 1e-6 &&
                    Math.abs(Number(line.getAttribute('y2')) - y) < 1e-6)
            """
            for endpoint in ([80, 0], [80, -40]):
                frame.wait_for_function(has_endpoint, arg=endpoint)
            canvas.locator("svg").press("Space")
            page.wait_for_function(
                "document.querySelector('#output').textContent.includes('callback received')"
            )
            frame.wait_for_function(has_endpoint, arg=[80, -60])
            self.assertEqual(errors, [])
            print(f"Pyodide ({label}): drawing and callback passed", flush=True)
        finally:
            (RESULTS / (label + ".txt")).write_text(
                page.locator("#status").inner_text(timeout=5000)
                + "\n"
                + page.locator("#output").inner_text(timeout=5000)
                + "\n"
                + "\n".join(errors)
            )
            page.screenshot(path=str(RESULTS / (label + ".png")))
            context.tracing.stop(path=str(RESULTS / (label + "-trace.zip")))
            context.close()
