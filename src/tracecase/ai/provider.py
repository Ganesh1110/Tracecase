"""AI provider protocol and implementations."""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Protocol, runtime_checkable

from tracecase.ai.models import Message

DEFAULT_AI_BASE_URL = os.getenv("TRACECASE_AI_BASE_URL", "http://127.0.0.1:8000/v1")
DEFAULT_AI_MODEL = os.getenv("TRACECASE_AI_MODEL", "default")

STRUCTURED_JSON_SYSTEM_PROMPT = (
    "You are a precise QA analysis engine. Respond with a single valid JSON object only. "
    "Do not include markdown code fences, commentary, or any text outside the JSON object."
)

_REQUEST_TIMEOUT_S = 30
_MAX_ATTEMPTS = 3


def parse_json_content(text: str) -> dict[str, Any]:
    """Parse a JSON object from model output, tolerating markdown code fences."""
    if not isinstance(text, str):
        return {}
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return {"content": text}
    return parsed if isinstance(parsed, dict) else {"content": parsed}


def _post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    *,
    timeout: int = _REQUEST_TIMEOUT_S,
    attempts: int = _MAX_ATTEMPTS,
) -> dict[str, Any]:
    """POST JSON with bounded retries on transient failures; return {} on failure."""
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 429) and exc.code < 500:
                return {}
        except json.JSONDecodeError:
            return {}
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        if attempt < attempts:
            time.sleep(0.2 * attempt)
    return {}


@runtime_checkable
class Provider(Protocol):
    """Protocol for AI language model providers."""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str | None: ...

    async def chat(
        self,
        messages: list[Message],
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send chat messages and return parsed JSON payload."""
        ...


class NullProvider:
    """Offline heuristic provider returning empty structures."""

    name: str = "null"
    model: str | None = None

    async def chat(
        self,
        messages: list[Message],
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {}


class OllamaProvider:
    """Provider connecting to local Ollama server."""

    name: str = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "llama3") -> None:
        self.base_url = base_url.rstrip("/")
        self.model: str | None = model

    def _sync_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = _post_json(
            f"{self.base_url}/api/chat",
            payload,
            {"Content-Type": "application/json"},
        )
        content = data.get("message", {}).get("content", "{}")
        if isinstance(content, str):
            return parse_json_content(content)
        return content if isinstance(content, dict) else {}

    async def chat(
        self,
        messages: list[Message],
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
        }
        if schema is not None:
            payload["format"] = "json"
        return await asyncio.to_thread(self._sync_request, payload)


class OpenAICompatProvider:
    """Provider connecting to OpenAI-compatible inference servers."""

    name: str = "openai"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000/v1",
        model: str = "default",
        api_key: str = "none",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model: str | None = model
        self.api_key = api_key

    def _sync_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = _post_json(
            f"{self.base_url}/chat/completions",
            payload,
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        choices = data.get("choices", [])
        if not choices:
            return {}
        content = choices[0].get("message", {}).get("content", "{}")
        if isinstance(content, str):
            return parse_json_content(content)
        return content if isinstance(content, dict) else {}

    async def chat(
        self,
        messages: list[Message],
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if schema is not None:
            payload["response_format"] = {"type": "json_object"}
        return await asyncio.to_thread(self._sync_request, payload)


def get_provider(
    name: str = "null",
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> Provider:
    """Factory creating an AI provider by name."""
    name_clean = name.lower().strip()
    if name_clean == "ollama":
        url = base_url or "http://127.0.0.1:11434"
        mdl = model or "llama3"
        return OllamaProvider(base_url=url, model=mdl)
    elif name_clean in {"openai", "vllm", "lmstudio"}:
        url = base_url or "http://127.0.0.1:8000/v1"
        mdl = model or "default"
        key = api_key or "none"
        return OpenAICompatProvider(base_url=url, model=mdl, api_key=key)
    return NullProvider()
