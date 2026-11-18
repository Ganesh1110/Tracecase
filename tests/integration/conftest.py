"""Fixtures for integration tests."""

import json
import threading
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

HTML = """<!doctype html>
<html>
  <body>
    <button id="load" onclick="fetch('/api/data').then(r => r.json()).then(d => {
      document.getElementById('out').textContent = d.source;
    })">Load</button>
    <button id="fail" onclick="fetch('/api/fail')">Fail</button>
    <button id="boom" onclick="throw new Error('boom')">Boom</button>
    <button id="submit" data-testid="submit-btn">Submit</button>
    <button id="plain">Plain</button>
    <div id="out"></div>
  </body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api/data":
            self._send(200, json.dumps({"source": "server"}).encode(), "application/json")
        elif self.path == "/api/fail":
            self._send(500, b'{"error": true}', "application/json")
        else:
            self._send(200, HTML.encode(), "text/html")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def html_server() -> Generator[str]:
    """Serve the integration fixture page on localhost."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
