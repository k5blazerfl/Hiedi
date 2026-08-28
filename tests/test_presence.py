"""The presence policy round-trips, tolerates junk, and gates proactive surfacing."""

from __future__ import annotations

from hiedi.core import presence
from hiedi.core.presence import Presence, PresenceLevel


def test_defaults_are_on_watch_and_quiet():
    p = Presence()
    assert p.level is PresenceLevel.ON_WATCH
    assert not p.level.proactive           # the default never speaks first
    assert not p.level.floats              # ...and draws no floating character
    assert p.dnd is False


def test_tier_capabilities():
    assert not PresenceLevel.ON_WATCH.floats
    assert PresenceLevel.ON_DECK.floats and not PresenceLevel.ON_DECK.proactive
    assert PresenceLevel.AT_YOUR_SIDE.proactive
    assert PresenceLevel.FIRST_MATE.proactive


def test_coerce_is_tolerant():
    assert PresenceLevel.coerce(2) is PresenceLevel.AT_YOUR_SIDE
    assert PresenceLevel.coerce("first_mate") is PresenceLevel.FIRST_MATE
    assert PresenceLevel.coerce("On Deck") is PresenceLevel.ON_DECK
    assert PresenceLevel.coerce(99) is PresenceLevel.ON_WATCH        # out of range
    assert PresenceLevel.coerce("nonsense") is PresenceLevel.ON_WATCH
    assert PresenceLevel.coerce(True) is PresenceLevel.ON_WATCH      # bool != level


def test_may_surface_respects_level_dnd_and_mutes():
    on_watch = Presence(level=PresenceLevel.ON_WATCH)
    assert not on_watch.may_surface("leg_ready")        # quiet tier: no bubbles

    active = Presence(level=PresenceLevel.AT_YOUR_SIDE)
    assert active.may_surface("leg_ready")

    dnd = Presence(level=PresenceLevel.FIRST_MATE, dnd=True)
    assert not dnd.may_surface("leg_ready")             # DND overrides the tier

    muted = Presence(level=PresenceLevel.AT_YOUR_SIDE, muted_kinds=["drift"])
    assert muted.muted("drift") and not muted.may_surface("drift")
    assert muted.may_surface("blocker")                 # other kinds still pass


def test_round_trip(tmp_path):
    path = tmp_path / "presence.yaml"
    p = Presence(level=PresenceLevel.AT_YOUR_SIDE, dnd=True, hourly_cap=5,
                 muted_kinds=["drift", "leg_ready"])
    presence.save(p, path)
    back = presence.load(path)
    assert back == p


def test_load_missing_and_malformed_are_defaults(tmp_path):
    assert presence.load(tmp_path / "nope.yaml") == Presence()
    junk = tmp_path / "junk.yaml"
    junk.write_text("- not: a mapping\n", encoding="utf-8")
    assert presence.load(junk) == Presence()


def test_config_path_honors_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert presence.config_path() == tmp_path / "hiedi" / "presence.yaml"
