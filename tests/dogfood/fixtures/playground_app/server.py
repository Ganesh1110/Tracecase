"""Standalone Playground Server on port 9000 for Tracecase dogfooding.

Serves plain HTML/JS pages (no frameworks) and deterministic REST endpoints:
- Forms, inputs, checkboxes, radios, select, textareas
- Action types: click, dblclick, hover, wait, navigate, check/uncheck, keypress, scroll
- Multi-tab (target=_blank, window.open)
- Console logging & unhandled JS errors
- Network endpoints (200, 4xx, 500, slow)
- Hostile XSS escaping targets
- Version-A (baseline), Version-B (healing tiers), Version-C (visual drift)
"""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PAGES_DIR = Path(__file__).parent / "pages"


class PlaygroundHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        # Suppress noisy standard request logging
        pass

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        # Endpoints
        if path == "/api/status/200":
            self._send_json({"status": 200, "message": "OK", "timestamp": time.time()})
            return
        if path == "/api/status/400":
            self._send_json({"error": "Bad Request", "code": 400}, status=400)
            return
        if path == "/api/status/403":
            self._send_json({"error": "Forbidden", "code": 403}, status=403)
            return
        if path == "/api/status/404":
            self._send_json({"error": "Not Found", "code": 404}, status=404)
            return
        if path == "/api/status/500":
            self._send_json({"error": "Internal Server Error", "code": 500}, status=500)
            return
        if path == "/api/slow":
            # Sleep 1.5s to test timeout sensitivity
            time.sleep(1.5)
            self._send_json({"delayed": True, "duration_ms": 1500})
            return
        if path == "/api/echo":
            query = parse_qs(parsed.query)
            self._send_json({"echo": query})
            return

        # Serve static HTML files
        clean_path = path.lstrip("/")
        if not clean_path or clean_path == "":
            clean_path = "index.html"
        if not clean_path.endswith(".html"):
            clean_path += ".html"

        file_path = PAGES_DIR / clean_path
        if file_path.exists() and file_path.is_file():
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        # Fallback 404
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"404 Not Found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""

        if path == "/api/login":
            try:
                data = json.loads(body) if body.startswith("{") else parse_qs(body)
            except Exception:
                data = {}
            # Valid creds check
            user = data.get("username", [""])[0] if isinstance(data.get("username"), list) else data.get("username")
            pwd = data.get("password", [""])[0] if isinstance(data.get("password"), list) else data.get("password")
            if user == "qa_user" and pwd == "secure_pass_123":
                self._send_json({"authenticated": True, "token": "tok_valid_test_session"})
            else:
                self._send_json({"authenticated": False, "error": "Invalid credentials"}, status=401)
            return

        if path == "/api/submit-unvalidated":
            self._send_json({"submitted": True, "received_length": len(body)})
            return

        if path == "/api/echo":
            self._send_json({"post_body": body})
            return

        self._send_json({"error": "Unknown POST endpoint"}, status=404)

    def _send_json(self, data: dict, status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class ReusableThreadingServer(ThreadingHTTPServer):
    allow_reuse_address = True
    allow_reuse_port = True
    daemon_threads = True


def create_playground_server(host: str = "127.0.0.1", port: int = 9000) -> ThreadingHTTPServer:
    return ReusableThreadingServer((host, port), PlaygroundHandler)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9010)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    server = create_playground_server(host=args.host, port=args.port)
    print(f"Playground server started on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
