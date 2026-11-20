"""Tests for AI provider abstraction and implementations."""

import json
import threading
import urllib.error
import urllib.request
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
    parse_json_content,
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

    def __enter__(self) -> "_MockResponse":
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


def test_parse_json_content_strips_markdown_fences() -> None:
    raw = '```json\n{"summary": "fenced"}\n```'
    assert parse_json_content(raw) == {"summary": "fenced"}


def test_parse_json_content_handles_plain_json() -> None:
    assert parse_json_content('{"summary": "plain"}') == {"summary": "plain"}


def test_parse_json_content_falls_back_to_content_on_invalid_json() -> None:
    assert parse_json_content("not json") == {"content": "not json"}


def _capture_urlopen(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any], *, fail_times: int = 0
) -> dict[str, int]:
    calls = {"n": 0}

    def _urlopen(req: Any, *args: Any, **kwargs: Any) -> _MockResponse:
        calls["n"] += 1
        if calls["n"] <= fail_times:
            raise urllib.error.URLError("temporary failure")
        captured["body"] = json.loads(req.data.decode("utf-8"))
        data = json.dumps(
            {"choices": [{"message": {"content": json.dumps({"ok": True})}}]}
        ).encode("utf-8")
        return _MockResponse(data)

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    return calls


@pytest.mark.asyncio
async def test_openai_provider_parses_fenced_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _urlopen(req: Any, *args: Any, **kwargs: Any) -> _MockResponse:
        data = json.dumps(
            {"choices": [{"message": {"content": '```json\n{"ok": true}\n```'}}]}
        ).encode("utf-8")
        return _MockResponse(data)

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    provider = OpenAICompatProvider(base_url="http://example.test/v1", model="m")
    assert await provider.chat([Message(role="user", content="hi")]) == {"ok": True}


@pytest.mark.asyncio
async def test_openai_provider_retries_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("tracecase.ai.provider.time.sleep", lambda _s: None)
    captured: dict[str, Any] = {}
    calls = _capture_urlopen(monkeypatch, captured, fail_times=2)
    provider = OpenAICompatProvider(base_url="http://example.test/v1", model="m")
    assert await provider.chat([Message(role="user", content="hi")]) == {"ok": True}
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_openai_provider_returns_empty_after_retry_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("tracecase.ai.provider.time.sleep", lambda _s: None)
    captured: dict[str, Any] = {}
    calls = _capture_urlopen(monkeypatch, captured, fail_times=99)
    provider = OpenAICompatProvider(base_url="http://example.test/v1", model="m")
    assert await provider.chat([Message(role="user", content="hi")]) == {}
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_openai_provider_requests_json_mode_when_schema_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    _capture_urlopen(monkeypatch, captured)
    provider = OpenAICompatProvider(base_url="http://example.test/v1", model="m")
    await provider.chat([Message(role="user", content="hi")], schema={})
    assert captured["body"]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_openai_provider_omits_json_mode_without_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    _capture_urlopen(monkeypatch, captured)
    provider = OpenAICompatProvider(base_url="http://example.test/v1", model="m")
    await provider.chat([Message(role="user", content="hi")])
    assert "response_format" not in captured["body"]


@pytest.mark.asyncio
async def test_ollama_provider_requests_json_format_when_schema_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _urlopen(req: Any, *args: Any, **kwargs: Any) -> _MockResponse:
        captured["body"] = json.loads(req.data.decode("utf-8"))
        data = json.dumps(
            {"message": {"role": "assistant", "content": json.dumps({"ok": True})}}
        ).encode("utf-8")
        return _MockResponse(data)

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    provider = OllamaProvider(base_url="http://example.test", model="llama3")
    await provider.chat([Message(role="user", content="hi")], schema={})
    assert captured["body"]["format"] == "json"
