"""The interruption budget paces proactive Notices atop the presence policy."""

from __future__ import annotations

from hiedi.core.budget import InterruptionBudget
from hiedi.core.presence import Presence, PresenceLevel


def _proactive(**kw) -> Presence:
    return Presence(level=PresenceLevel.AT_YOUR_SIDE, **kw)


def test_standing_policy_gates_first():
    # On Watch is not a proactive tier — nothing surfaces regardless of budget
    b = InterruptionBudget(Presence(level=PresenceLevel.ON_WATCH))
    assert not b.allows("leg_ready", now=0.0)

    # DND and per-kind mutes also block (delegated to Presence.may_surface)
    assert not InterruptionBudget(_proactive(dnd=True)).allows("leg_ready", now=0.0)
    muted = InterruptionBudget(_proactive(muted_kinds=["drift"]))
    assert not muted.allows("drift", now=0.0)
    assert muted.allows("blocker", now=0.0)


def test_focus_guard_blocks():
    b = InterruptionBudget(_proactive())
    assert b.allows("leg_ready", now=0.0, focus_ok=True)
    assert not b.allows("leg_ready", now=0.0, focus_ok=False)  # fullscreen/not focused


def test_hourly_cap():
    b = InterruptionBudget(_proactive(hourly_cap=2), window_s=3600.0)
    assert b.surface("leg_ready", now=0.0)      # 1
    assert b.surface("leg_ready", now=10.0)     # 2
    assert not b.allows("leg_ready", now=20.0)  # over cap
    assert b.remaining(20.0) == 0


def test_window_expiry_reopens_budget():
    b = InterruptionBudget(_proactive(hourly_cap=1), window_s=100.0)
    assert b.surface("leg_ready", now=0.0)
    assert not b.allows("leg_ready", now=50.0)   # still inside the window
    assert b.allows("leg_ready", now=101.0)      # the old one aged out
    assert b.remaining(101.0) == 1


def test_per_kind_cooldown():
    b = InterruptionBudget(_proactive(hourly_cap=10), cooldown_s=60.0)
    assert b.surface("drift", now=0.0)
    assert not b.allows("drift", now=30.0)       # same kind, too soon
    assert b.allows("blocker", now=30.0)         # a different kind is unaffected
    assert b.allows("drift", now=60.0)           # cooldown elapsed


def test_remaining_unlimited_when_cap_disabled():
    b = InterruptionBudget(_proactive(hourly_cap=0))
    b.surface("leg_ready", now=0.0)
    assert b.remaining(0.0) >= 1000
    assert b.allows("leg_ready", now=0.0)        # no cap → always allowed by budget
