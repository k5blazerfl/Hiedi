"""The ``Brain`` contract shared by every backend.

Deliberately tiny: a brain turns a list of messages into a reply, optionally streaming
tokens. Keeping the surface this small is what lets ``OllamaBrain`` and ``ClaudeBrain``
be interchangeable and lets tests inject a fake with no network at all.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Message:
    role: str          # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class Reply:
    """A completed reply plus the attribution that must travel with it."""

    content: str
    brain: str         # "local" | "cloud"
    model: str         # the concrete model id, e.g. "qwen3-coder:latest"


class BrainError(RuntimeError):
    """Any failure talking to a model backend (network, HTTP, bad payload)."""


@runtime_checkable
class Brain(Protocol):
    """A model backend. ``name``/``model`` feed attribution; ``chat`` does the work."""

    #: "local" or "cloud" — the coarse identity the UI shows.
    name: str
    #: the concrete model id used for the reply's ``model:`` stamp.
    model: str

    def available(self) -> bool:
        """Cheap best-effort check that this brain can be reached right now."""
        ...

    def chat(self, messages: list[Message], *, temperature: float = 0.7) -> Reply:
        """Return a completed reply. Raises :class:`BrainError` on failure."""
        ...

    def stream(self, messages: list[Message], *, temperature: float = 0.7) -> Iterator[str]:
        """Yield content tokens as they arrive. Raises :class:`BrainError` on failure."""
        ...
