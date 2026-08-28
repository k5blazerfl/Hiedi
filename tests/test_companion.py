"""The companion renders Notices per tier + budget (offscreen, PySide6 required)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")  # skip where the qt extra isn't installed

from PySide6.QtWidgets import QApplication  # noqa: E402

from hiedi.core.notices import Notice, NoticeKind  # noqa: E402
from hiedi.core.presence import Presence, PresenceLevel  # noqa: E402
from hiedi.core.presenter import Presentation  # noqa: E402
from hiedi.ui.companion import Companion  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _notice(kind=NoticeKind.LEG_READY):
    return Notice(kind, "v", "Ready to start", "Its prerequisites are done.")


def test_on_watch_toasts(app):
    c = Companion(Presence(level=PresenceLevel.ON_WATCH), clock=lambda: 0.0)
    assert c.handle_notice(_notice()) is Presentation.TOAST


def test_on_deck_is_pose(app):
    c = Companion(Presence(level=PresenceLevel.ON_DECK), clock=lambda: 0.0)
    assert c.handle_notice(_notice()) is Presentation.POSE


def test_proactive_bubbles_then_toasts_over_budget(app):
    c = Companion(Presence(level=PresenceLevel.FIRST_MATE, hourly_cap=1), clock=lambda: 0.0)
    assert c.handle_notice(_notice()) is Presentation.BUBBLE   # bubble is shown
    assert not c._bubble.isHidden()                             # un-hidden (window not shown offscreen)
    assert "Ready to start" in c._bubble.text()
    assert c.handle_notice(_notice()) is Presentation.TOAST     # budget spent → quiet


def test_muted_kind_is_silent(app):
    c = Companion(Presence(level=PresenceLevel.FIRST_MATE, muted_kinds=["leg_ready"]),
                  clock=lambda: 0.0)
    assert c.handle_notice(_notice()) is Presentation.NONE


def test_status_sets_pose(app):
    c = Companion(Presence(), clock=lambda: 0.0)
    c.set_status("thinking")   # must not raise; pose swaps in the reused MascotImage
    assert c._mascot.pixmap() is not None


def test_dial_persists_presence(app, tmp_path, monkeypatch):
    import hiedi.core.presence as pm
    monkeypatch.setattr(pm, "config_path", lambda: tmp_path / "presence.yaml")
    c = Companion(Presence(level=PresenceLevel.ON_WATCH), clock=lambda: 0.0)
    c.set_level(PresenceLevel.AT_YOUR_SIDE)
    assert pm.load().level is PresenceLevel.AT_YOUR_SIDE


def test_dnd_toggle_persists_and_silences(app, tmp_path, monkeypatch):
    import hiedi.core.presence as pm
    monkeypatch.setattr(pm, "config_path", lambda: tmp_path / "presence.yaml")
    c = Companion(Presence(level=PresenceLevel.FIRST_MATE), clock=lambda: 0.0)
    c.toggle_dnd(True)
    assert pm.load().dnd is True
    assert c.handle_notice(_notice()) is Presentation.POSE   # DND → pose only, no bubble


def test_quick_menu_has_controls(app):
    c = Companion(Presence(level=PresenceLevel.ON_DECK), clock=lambda: 0.0)
    menu = c.build_menu()
    texts = [a.text() for a in menu.actions()]
    assert "Do Not Disturb" in texts and "Send below deck" in texts
    # the Presence submenu marks the current tier as checked
    submenu = next(a.menu() for a in menu.actions() if a.menu() is not None)
    checked = [a.text() for a in submenu.actions() if a.isChecked()]
    assert checked == ["On Deck"]
