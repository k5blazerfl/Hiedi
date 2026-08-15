"""The Ollama brain parses correctly and the router honors the consent gate."""

from __future__ import annotations

import pytest

from hiedi.core.brain import OllamaBrain, Router
from hiedi.core.brain.base import BrainError, Message
from hiedi.core.brain.claude import ClaudeBrain, ClaudeUnavailable
from hiedi.core.model import Consent, VoyageConfig


def _transport(chat_content="hello"):
    def t(url, payload, stream):
        if url.endswith("/api/tags"):
            return {"models": []}
        if stream:
            return iter([{"message": {"content": "he"}}, {"message": {"content": "llo"}}])
        return {"message": {"content": chat_content}}
    return t


def test_ollama_chat_and_stream():
    b = OllamaBrain(transport=_transport("  charted  "))
    assert b.available() is True
    assert b.chat([Message("user", "hi")]).content == "charted"
    assert "".join(b.stream([Message("user", "hi")])) == "hello"


def test_ollama_bad_payload_raises():
    def bad(url, payload, stream):
        return {"nope": True}
    with pytest.raises(BrainError):
        OllamaBrain(transport=bad).chat([Message("user", "hi")])


def test_router_default_is_local():
    r = Router(OllamaBrain(transport=_transport()))
    _, d = r.choose(VoyageConfig())
    assert d.brain == "local" and not d.fell_back


def test_router_ask_gate_requires_consent():
    r = Router(OllamaBrain(transport=_transport()), ClaudeBrain())
    cfg = VoyageConfig()  # cloud=ask
    assert r.needs_cloud_consent(cfg, want_cloud=True) is True
    _, no = r.choose(cfg, want_cloud=True, consented=False)
    assert no.brain == "local" and no.fell_back            # no consent -> stay local
    _, yes = r.choose(cfg, want_cloud=True, consented=True)
    assert yes.brain == "cloud"


def test_router_never_gate_blocks_cloud():
    r = Router(OllamaBrain(transport=_transport()), ClaudeBrain())
    cfg = VoyageConfig()
    cfg.cloud = Consent.NEVER
    _, d = r.choose(cfg, want_cloud=True, consented=True)
    assert d.brain == "local" and d.fell_back


def test_router_falls_back_when_cloud_fails():
    cfg = VoyageConfig()
    cfg.cloud = Consent.ALLOW
    r = Router(OllamaBrain(transport=_transport("safe")), ClaudeBrain())
    reply, d = r.chat(cfg, [Message("user", "hi")], want_cloud=True)
    # ClaudeBrain raises ClaudeUnavailable -> router falls back to local
    assert reply.content == "safe" and d.fell_back and d.brain == "local"


def test_claude_unavailable_without_key():
    with pytest.raises(ClaudeUnavailable):
        ClaudeBrain(key_resolver=lambda: None).chat([Message("user", "hi")])
