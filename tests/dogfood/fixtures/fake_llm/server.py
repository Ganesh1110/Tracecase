"""Fake OpenAI and Ollama compatible LLM server on port 9100 for Tracecase dogfooding.

Supports modes:
- deterministic (default): structured JSON analysis, assertions, recommendations
- malformed: returns invalid JSON syntax
- 500: returns HTTP 500 Internal Server Error
- slow / timeout: sleeps 5s before replying
- ollama: responds to /api/tags, /api/chat, /api/generate
"""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class FakeLLMHandler(BaseHTTPRequestHandler):
    current_mode: str = "deterministic"
    received_requests: list[dict] = []

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        # Control endpoint to get received requests or reset
        if path == "/mock/history":
            self._send_json(self.received_requests)
            return
        if path == "/mock/reset":
            self.received_requests.clear()
            FakeLLMHandler.current_mode = "deterministic"
            self._send_json({"status": "reset"})
            return

        # OpenAI /v1/models
        if path in ("/v1/models", "/models"):
            self._send_json({
                "object": "list",
                "data": [
                    {"id": "gpt-4o", "object": "model", "owned_by": "mock"},
                    {"id": "gpt-4o-mini", "object": "model", "owned_by": "mock"},
                ]
            })
            return

        # Ollama /api/tags
        if path in ("/api/tags", "/tags"):
            self._send_json({
                "models": [
                    {"name": "llama3:latest", "model": "llama3:latest"},
                    {"name": "qwen2.5:latest", "model": "qwen2.5:latest"},
                ]
            })
            return

        self._send_json({"status": "ok", "mock_server": "fake_llm", "mode": self.current_mode})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        # Mode configuration endpoint: POST /mock/mode?mode=500|malformed|slow|deterministic
        if path == "/mock/mode":
            query = parse_qs(parsed.query)
            mode = query.get("mode", ["deterministic"])[0]
            FakeLLMHandler.current_mode = mode
            self._send_json({"mode": FakeLLMHandler.current_mode})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        try:
            req_data = json.loads(body) if body else {}
        except Exception:
            req_data = {"raw": body}

        # Check mode from header or server state
        mode = self.headers.get("X-Mock-Mode", FakeLLMHandler.current_mode)

        # Log payload for Privacy & Metadata verification (Flow M2)
        self.received_requests.append({
            "path": path,
            "headers": dict(self.headers),
            "payload": req_data,
            "timestamp": time.time(),
        })

        if mode == "500":
            self._send_json({"error": {"message": "Simulated LLM Server 500 Error", "type": "server_error"}}, status=500)
            return

        if mode == "slow":
            time.sleep(3.0)

        if mode == "malformed":
            payload = b"{not a valid json syntax: error"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # OpenAI /v1/chat/completions
        if path in ("/v1/chat/completions", "/chat/completions"):
            ai_reply = {
                "summary": "Mock AI Analysis: Flow records critical user interactions.",
                "risk_score": 45,
                "risks": [
                    {"category": "security", "severity": "medium", "description": "Form input lacks explicit CSP protection"}
                ],
                "recommended_assertions": [
                    {"type": "element_visible", "selector": "#btn-login", "description": "Verify login button remains visible"}
                ],
                "negative_proposals": [
                    {"type": "boundary", "description": "Submit form with empty credentials"}
                ],
            }
            response = {
                "id": "chatcmpl-mock-123",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": req_data.get("model", "gpt-4o"),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(ai_reply),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 100, "total_tokens": 150},
            }
            self._send_json(response)
            return

        # Ollama /api/chat
        if path in ("/api/chat", "/chat"):
            response = {
                "model": req_data.get("model", "llama3"),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "summary": "Ollama Mock AI Analysis",
                        "risk_score": 30,
                        "risks": [],
                        "recommended_assertions": [],
                    }),
                },
                "done": True,
            }
            self._send_json(response)
            return

        # Ollama /api/generate
        if path in ("/api/generate", "/generate"):
            response = {
                "model": req_data.get("model", "llama3"),
                "response": "Generated mock response from Ollama API",
                "done": True,
            }
            self._send_json(response)
            return

        self._send_json({"error": "Unknown Fake LLM endpoint"}, status=404)

    def _send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class ReusableFakeLLMServer(ThreadingHTTPServer):
    allow_reuse_address = True
    allow_reuse_port = True
    daemon_threads = True


def create_fake_llm_server(host: str = "127.0.0.1", port: int = 9100) -> ThreadingHTTPServer:
    return ReusableFakeLLMServer((host, port), FakeLLMHandler)


if __name__ == "__main__":
    server = create_fake_llm_server()
    print("Fake LLM server started on http://127.0.0.1:9100")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
