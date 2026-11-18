"""AI provider protocol and implementations."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any, Protocol, runtime_checkable

from qa_auto.ai.models import Message


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
        url = f"{self.base_url}/api/chat"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data.get("message", {}).get("content", "{}")
                if isinstance(content, str):
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {"content": content}
                return content if isinstance(content, dict) else {}
        except Exception:
            return {}

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
        url = f"{self.base_url}/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "{}")
                    if isinstance(content, str):
                        try:
                            return json.loads(content)
                        except json.JSONDecodeError:
                            return {"content": content}
                    return content if isinstance(content, dict) else {}
                return {}
        except Exception:
            return {}

    async def chat(
        self,
        messages: list[Message],
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
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
