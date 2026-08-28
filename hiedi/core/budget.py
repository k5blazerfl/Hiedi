"""The interruption budget — runtime pacing for proactive Notices (tiers 2-3).

Layered on top of the *standing* presence policy (:meth:`Presence.may_surface`, the
config-level gate): even when the tier is proactive and a kind isn't muted, the
budget caps how often Hiedi actually speaks unprompted — an hourly cap (from the
presence policy), an optional per-kind cooldown, and a focus/fullscreen guard the
caller supplies. This is the runtime layer the companion holds; the config layer
(:mod:`hiedi.core.presence`) stays pure standing policy.

Pure and clock-injected: the caller passes ``now`` as epoch seconds (monotonic or
wall — the budget only ever subtracts), so it unit-tests without a display or a real
clock. See ``docs/desktop-assistant.md`` §6.
"""

from __future__ import annotations

from typing import Any

from .presence import Presence


class InterruptionBudget:
    """Tracks recent proactive surfacings and decides whether the next may fire."""

    def __init__(self, presence: Presence, *, window_s: float = 3600.0,
                 cooldown_s: float = 0.0) -> None:
        self.presence = presence
        self.window_s = window_s          # the "hourly" cap window
        self.cooldown_s = cooldown_s      # per-kind minimum gap (0 = none)
        self._recent: list[tuple[float, str]] = []  # (timestamp, kind), pruned to window

    @staticmethod
    def _key(kind: Any) -> str:
        return getattr(kind, "value", kind)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_s
        self._recent = [(t, k) for (t, k) in self._recent if t >= cutoff]

    def allows(self, kind: Any, *, now: float, focus_ok: bool = True) -> bool:
        """Whether a proactive surfacing of ``kind`` may fire right now.

        Combines, in order: the standing policy (proactive tier, not DND, not
        muted), the caller's focus/fullscreen guard, the hourly cap, and the
        per-kind cooldown. Read-only — call :meth:`record` (or :meth:`surface`)
        once the notice actually goes out.
        """
        if not self.presence.may_surface(kind):
            return False              # wrong tier / DND / kind muted
        if not focus_ok:
            return False              # fullscreen, presentation, not focused, …
        self._prune(now)
        cap = self.presence.hourly_cap
        if cap > 0 and len(self._recent) >= cap:
            return False              # over the hourly budget
        if self.cooldown_s > 0:
            k = self._key(kind)
            last = max((t for (t, kk) in self._recent if kk == k), default=None)
            if last is not None and now - last < self.cooldown_s:
                return False          # this kind fired too recently
        return True

    def record(self, kind: Any, *, now: float) -> None:
        """Note that a proactive surfacing of ``kind`` went out at ``now``."""
        self._prune(now)
        self._recent.append((now, self._key(kind)))

    def surface(self, kind: Any, *, now: float, focus_ok: bool = True) -> bool:
        """Atomic allow-and-record: fire if permitted, recording it; else False."""
        if self.allows(kind, now=now, focus_ok=focus_ok):
            self.record(kind, now=now)
            return True
        return False

    def remaining(self, now: float) -> int:
        """Proactive surfacings still allowed in the current window (cap-limited)."""
        self._prune(now)
        cap = self.presence.hourly_cap
        if cap <= 0:
            return 1_000_000          # cap disabled — effectively unlimited
        return max(0, cap - len(self._recent))


__all__ = ["InterruptionBudget"]
