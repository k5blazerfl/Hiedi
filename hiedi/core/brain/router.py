"""The model router — chooses local vs cloud and enforces the consent gate.

Routing rules (all derived from the per-Voyage :class:`~hiedi.core.model.VoyageConfig`):

* Default is ``routing.default`` (``local`` unless the Voyage escalates).
* The cloud brain is reachable **only** if the Voyage ``cloud`` consent is not ``never``.
  ``allow`` uses cloud silently when asked; ``ask`` means the *caller* must have already
  obtained consent for this turn (the router exposes :meth:`needs_cloud_consent` so the
  daemon/UI can prompt) — the router itself never reaches the cloud past a ``never`` gate.
* If the chosen brain is unavailable, the router falls back to local and says so.

Every reply carries attribution from the brain; :class:`RoutingDecision` records *why*
that brain was chosen so the UI can be honest about it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model import Consent, VoyageConfig
from .base import Brain, BrainError, Message, Reply


@dataclass(frozen=True)
class RoutingDecision:
    brain: str          # "local" | "cloud"
    model: str
    reason: str         # human-readable: why this brain
    fell_back: bool = False


class Router:
    def __init__(self, local: Brain, cloud: Brain | None = None) -> None:
        self.local = local
        self.cloud = cloud

    # -- gate helpers ------------------------------------------------------------

    def cloud_allowed(self, config: VoyageConfig) -> bool:
        """True if the Voyage's consent policy permits the cloud brain at all."""
        return self.cloud is not None and config.cloud is not Consent.NEVER

    def needs_cloud_consent(self, config: VoyageConfig, *, want_cloud: bool) -> bool:
        """True when a per-turn prompt is required before using the cloud brain."""
        return (want_cloud and self.cloud is not None
                and config.cloud is Consent.ASK)

    # -- selection ---------------------------------------------------------------

    def choose(
        self,
        config: VoyageConfig,
        *,
        want_cloud: bool = False,
        consented: bool = False,
    ) -> tuple[Brain, RoutingDecision]:
        """Pick the brain to use for a turn, honoring the consent gate.

        ``want_cloud`` = the caller asked for cloud (explicit escalation).
        ``consented`` = a per-turn cloud prompt was answered yes (relevant when the
        Voyage gate is ``ask``).
        """
        use_cloud = want_cloud or config.routing.default == "cloud"

        if use_cloud and self.cloud_allowed(config):
            gate = config.cloud
            ok = gate is Consent.ALLOW or (gate is Consent.ASK and consented)
            if ok and self.cloud is not None:
                return self.cloud, RoutingDecision(
                    brain="cloud", model=self.cloud.model,
                    reason="escalated to the cloud brain (consent satisfied)")
            # Wanted cloud but consent not (yet) given -> stay local, be explicit.
            return self.local, RoutingDecision(
                brain="local", model=self.local.model, fell_back=True,
                reason="cloud requested but consent not granted; used the local brain")

        if use_cloud and not self.cloud_allowed(config):
            return self.local, RoutingDecision(
                brain="local", model=self.local.model, fell_back=True,
                reason="cloud disabled for this Voyage; used the local brain")

        return self.local, RoutingDecision(
            brain="local", model=self.local.model,
            reason="local brain (default)")

    # -- execution ---------------------------------------------------------------

    def chat(
        self,
        config: VoyageConfig,
        messages: list[Message],
        *,
        want_cloud: bool = False,
        consented: bool = False,
        temperature: float = 0.7,
    ) -> tuple[Reply, RoutingDecision]:
        """Route and run a chat turn, falling back to local on a cloud failure."""
        brain, decision = self.choose(config, want_cloud=want_cloud, consented=consented)
        try:
            reply = brain.chat(messages, temperature=temperature)
        except BrainError:
            if brain is self.local:
                raise
            reply = self.local.chat(messages, temperature=temperature)
            decision = RoutingDecision(
                brain="local", model=self.local.model, fell_back=True,
                reason="cloud brain failed; fell back to the local brain")
        return reply, decision


__all__ = ["Router", "RoutingDecision"]
