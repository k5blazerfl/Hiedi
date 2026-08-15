"""The cloud brain — Claude — stubbed for the MVP but wired into the router.

Two things are deliberately settled here so enabling it later is a small, safe change:

1. **Where the key comes from.** Never a file, never an env var baked into config: the
   Anthropic API key is fetched at call time from HeDE's **Keychain over the Secret
   Service session bus** (``org.freedesktop.secrets``) — the same integration any
   libsecret client uses. :func:`fetch_api_key` documents the lookup; the daemon injects
   a resolver so the pure core never imports a bus binding.
2. **The gate is upstream.** By the time a call reaches here the router has already
   checked the per-Voyage ``cloud`` consent. This class never bypasses that.

Until the Messages-API call is implemented, :meth:`chat` raises
:class:`ClaudeUnavailable`; the router treats that as "fall back to local / surface a
clear message", and the UI greys the Claude toggle.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from .base import BrainError, Message, Reply

DEFAULT_MODEL = "claude-opus-4-8"

# The daemon passes a resolver that looks the key up in the Secret Service vault. The
# expected lookup attributes (documented for the implementer):
#   {"service": "anthropic", "purpose": "hiedi-cloud-brain"}
KeyResolver = Callable[[], str | None]


class ClaudeUnavailable(BrainError):
    """Raised when the cloud brain is selected but not usable (no key / not implemented)."""


def fetch_api_key(resolver: KeyResolver | None) -> str | None:
    """Resolve the Anthropic key via the injected Secret Service resolver, or None."""
    if resolver is None:
        return None
    try:
        return resolver()
    except Exception:
        return None


class ClaudeBrain:
    name = "cloud"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        key_resolver: KeyResolver | None = None,
    ) -> None:
        self.model = model
        self._key_resolver = key_resolver

    def available(self) -> bool:
        # Wired, not yet implemented: available only once both a key exists AND the
        # Messages-API call below is built. Today the second half is missing.
        return False

    def _require(self) -> str:
        key = fetch_api_key(self._key_resolver)
        if not key:
            raise ClaudeUnavailable(
                "No Anthropic key in the Keychain. Store one, then enable the cloud brain.")
        # TODO(mvp+1): implement the Anthropic Messages API call (streaming + non-stream)
        # using `key`. Kept out of the MVP by decision (Ollama-only first).
        raise ClaudeUnavailable("The Claude brain is wired but not enabled yet.")

    def chat(self, messages: list[Message], *, temperature: float = 0.7) -> Reply:
        self._require()
        raise AssertionError("unreachable")  # _require always raises today

    def stream(self, messages: list[Message], *, temperature: float = 0.7) -> Iterator[str]:
        self._require()
        yield ""  # pragma: no cover — unreachable today
