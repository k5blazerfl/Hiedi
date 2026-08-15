"""The brain layer — a pluggable model router.

``local`` (Ollama) is the default brain: private, offline, free. ``cloud`` (Claude) is
an optional heavy-reasoning pilot, gated per-Voyage. The router picks between them and
stamps ``model:`` attribution on everything, so the UI can always show *which brain
answered* and nothing reaches the cloud without the consent gate saying yes.
"""

from .base import Brain, BrainError, Message, Reply
from .ollama import OllamaBrain
from .claude import ClaudeBrain, ClaudeUnavailable
from .router import Router, RoutingDecision

__all__ = [
    "Brain", "BrainError", "Message", "Reply",
    "OllamaBrain", "ClaudeBrain", "ClaudeUnavailable",
    "Router", "RoutingDecision",
]
