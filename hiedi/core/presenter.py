"""How an incoming Notice becomes a presentation — the companion's decision brain.

Pure policy tying the presence tier + the interruption budget together: given a
Notice and the current context (now, whether the foreground is safe to interrupt),
it returns *how* the companion should surface it — nothing, a pose change, a bar
toast, or a speech bubble. The Qt companion renders the verdict; this module holds
the logic so it unit-tests with no display. See ``docs/desktop-assistant.md`` §3/§6.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from .budget import InterruptionBudget
from .presence import Presence, PresenceLevel


class Presentation(str, Enum):
    NONE = "none"       # silenced — the kind is muted
    POSE = "pose"       # reflect in the mascot's pose only (ambient / Do Not Disturb)
    TOAST = "toast"     # a bar toast (+ breathing pin) — the On Watch surface
    BUBBLE = "bubble"   # a speech bubble from the companion (proactive tiers)


def decide(notice: Any, presence: Presence, budget: InterruptionBudget, *,
           now: float, focus_ok: bool = True) -> Presentation:
    """Decide how to surface ``notice`` right now.

    Order: a muted kind is silenced; Do Not Disturb stays pose-only; then the tier
    decides — On Watch toasts, On Deck reflects in the pose, and the proactive tiers
    try a **budgeted** bubble (consuming a budget slot only when the verdict is
    BUBBLE), falling back to a quiet toast when the budget is spent or the
    foreground isn't safe to interrupt.
    """
    if presence.muted(notice.kind):
        return Presentation.NONE
    if presence.dnd:
        return Presentation.POSE

    level = presence.level
    if level is PresenceLevel.ON_WATCH:
        return Presentation.TOAST
    if level is PresenceLevel.ON_DECK:
        return Presentation.POSE

    # At Your Side / First Mate: a bubble if the budget (and focus) allow, else a
    # quiet toast. budget.surface() records the firing exactly when we choose BUBBLE.
    if focus_ok and budget.surface(notice.kind, now=now, focus_ok=focus_ok):
        return Presentation.BUBBLE
    return Presentation.TOAST


__all__ = ["Presentation", "decide"]
