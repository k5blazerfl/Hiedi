"""The presenter maps a Notice to a presentation per tier + budget."""

from __future__ import annotations

from hiedi.core.budget import InterruptionBudget
from hiedi.core.notices import Notice, NoticeKind
from hiedi.core.presence import Presence, PresenceLevel
from hiedi.core.presenter import Presentation, decide


def _notice(kind=NoticeKind.LEG_READY):
    return Notice(kind, "v", "Ready to start")


def _budget(presence):
    return InterruptionBudget(presence)


def test_muted_kind_is_silenced():
    p = Presence(level=PresenceLevel.FIRST_MATE, muted_kinds=["leg_ready"])
    assert decide(_notice(), p, _budget(p), now=0.0) is Presentation.NONE


def test_dnd_is_pose_only():
    p = Presence(level=PresenceLevel.FIRST_MATE, dnd=True)
    assert decide(_notice(), p, _budget(p), now=0.0) is Presentation.POSE


def test_on_watch_toasts():
    p = Presence(level=PresenceLevel.ON_WATCH)
    assert decide(_notice(), p, _budget(p), now=0.0) is Presentation.TOAST


def test_on_deck_is_pose():
    p = Presence(level=PresenceLevel.ON_DECK)
    assert decide(_notice(), p, _budget(p), now=0.0) is Presentation.POSE


def test_proactive_bubbles_and_consumes_budget():
    p = Presence(level=PresenceLevel.AT_YOUR_SIDE, hourly_cap=1)
    b = _budget(p)
    assert decide(_notice(), p, b, now=0.0) is Presentation.BUBBLE
    assert b.remaining(0.0) == 0                                   # slot consumed
    # next one is over budget → falls back to a quiet toast
    assert decide(_notice(), p, b, now=1.0) is Presentation.TOAST


def test_proactive_without_focus_falls_back_to_toast():
    p = Presence(level=PresenceLevel.AT_YOUR_SIDE, hourly_cap=5)
    b = _budget(p)
    assert decide(_notice(), p, b, now=0.0, focus_ok=False) is Presentation.TOAST
    assert b.remaining(0.0) == 5                                   # no slot spent when not bubbling
