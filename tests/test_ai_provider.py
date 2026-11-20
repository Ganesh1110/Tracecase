"""Tests for AI provider abstraction and implementations."""

import json
import threading
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from tracecase.ai.models import Message
from tracecase.ai.provider import (
    NullProvider,
    OllamaProvider,
    OpenAICompatProvider,
    get_provider,
)


class _MockLLMHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        content_len = int(self.headers.get("Content-Length", "0"))
        if content_len:
            self.rfile.read(content_len)

        if self.path == "/api/chat":
            resp = {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"summary": "Ollama response"}),
                }
            }
            self._send(200, resp)
        elif self.path == "/v1/chat/completions":
            resp = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"summary": "OpenAI response"}),
                        }
                    }
                ]
            }
            self._send(200, resp)
        else:
            self.send_response(404)
            self.end_headers()

    def _send(self, status: int, data: dict[str, Any]) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


class _MockResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> _MockResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


@pytest.fixture
def mock_llm_server(monkeypatch: pytest.MonkeyPatch) -> Generator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockLLMHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def _mock_urlopen(req: Any, *args: Any, **kwargs: Any) -> Any:
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/api/chat" in url:
            data = json.dumps({
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"summary": "Ollama response"}),
                }
            }).encode("utf-8")
            return _MockResponse(data)
        elif "/v1/chat/completions" in url:
            data = json.dumps({
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"summary": "OpenAI response"}),
                        }
                    }
                ]
            }).encode("utf-8")
            return _MockResponse(data)
        return _MockResponse(b"{}")

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", _mock_urlopen)

    try:
        yield base
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_null_provider_returns_empty_content() -> None:
    provider = NullProvider()
    assert provider.name == "null"
    resp = await provider.chat([Message(role="user", content="hello")])
    assert resp == {}


@pytest.mark.asyncio
async def test_ollama_provider_chats(mock_llm_server: str) -> None:
    provider = OllamaProvider(base_url=mock_llm_server, model="llama3")
    resp = await provider.chat([Message(role="user", content="hello")])
    assert resp == {"summary": "Ollama response"}


@pytest.mark.asyncio
async def test_openai_compat_provider_chats(mock_llm_server: str) -> None:
    provider = OpenAICompatProvider(base_url=f"{mock_llm_server}/v1", model="gpt-4o")
    resp = await provider.chat([Message(role="user", content="hello")])
    assert resp == {"summary": "OpenAI response"}


def test_get_provider_factory() -> None:
    assert isinstance(get_provider("null"), NullProvider)
    assert isinstance(get_provider("ollama"), OllamaProvider)
    assert isinstance(get_provider("openai"), OpenAICompatProvider)
