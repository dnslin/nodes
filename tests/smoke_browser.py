"""Offline browser smoke: localhost page, headed Chromium, bundled extension."""

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from DrissionPage import Chromium

from browser_runtime import browser_options


class SmokePage(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<!doctype html><title>Nodes browser smoke</title><h1 id='result'>Ready</h1>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), SmokePage)
    Thread(target=server.serve_forever, daemon=True).start()
    browser = None
    try:
        options = browser_options(hidden=True)
        browser = Chromium(options)
        tab = browser.latest_tab
        tab.get(f"http://127.0.0.1:{server.server_port}/")
        assert tab.title == "Nodes browser smoke", tab.title
        assert tab.ele("#result").text == "Ready"
        assert "HeadlessChrome" not in tab.run_js("return navigator.userAgent")
        assert tab.run_js("return Array.isArray(navigator.plugins)") is True, (
            "Turnstile extension did not run in the page world"
        )
        assert tab.run_js("return navigator.webdriver") is False
        print("PASS: headed Chromium loaded a localhost page and the bundled MV3 extension.")
    finally:
        if browser is not None:
            browser.quit()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
