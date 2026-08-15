"""The local brain — Ollama over its HTTP API, stdlib only.

Reuses the convention already established in ``~/hiedi-lab`` (``OLLAMA_HOST``,
``HIEDI_MODEL``, ``POST /api/chat``) so Hiedi-the-assistant and the mascot art tooling
speak to the same server the same way. The HTTP call goes through an injectable
``transport`` so tests exercise the parsing without a running model.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator

from .base import BrainError, Message, Reply

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("HIEDI_MODEL", "qwen3-coder:latest")

# transport(url, payload, stream) -> for stream=False a dict; for stream=True an
# iterator of dicts (one per streamed chunk). Injected in tests.
Transport = Callable[[str, dict, bool], object]


def _http_transport(url: str, payload: dict, stream: bool):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=600)
    except (urllib.error.URLError, OSError) as e:
        raise BrainError(f"cannot reach Ollama at {url}: {e}") from e
    if not stream:
        with resp:
            return json.loads(resp.read().decode())

    def gen():
        with resp:
            for raw in resp:
                raw = raw.strip()
                if raw:
                    yield json.loads(raw.decode())
    return gen()


class OllamaBrain:
    name = "local"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        host: str = DEFAULT_HOST,
        transport: Transport = _http_transport,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self._transport = transport

    def _payload(self, messages: list[Message], temperature: float, stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
            "options": {"temperature": temperature},
        }

    def available(self) -> bool:
        try:
            self._transport(f"{self.host}/api/tags", {}, False)
            return True
        except Exception:
            return False

    def chat(self, messages: list[Message], *, temperature: float = 0.7) -> Reply:
        data = self._transport(
            f"{self.host}/api/chat", self._payload(messages, temperature, False), False)
        try:
            content = data["message"]["content"]  # type: ignore[index]
        except (KeyError, TypeError) as e:
            raise BrainError(f"unexpected Ollama response: {data!r}") from e
        return Reply(content=content.strip(), brain=self.name, model=self.model)

    def stream(self, messages: list[Message], *, temperature: float = 0.7) -> Iterator[str]:
        chunks = self._transport(
            f"{self.host}/api/chat", self._payload(messages, temperature, True), True)
        for chunk in chunks:  # type: ignore[union-attr]
            msg = chunk.get("message") if isinstance(chunk, dict) else None
            if msg and msg.get("content"):
                yield msg["content"]
