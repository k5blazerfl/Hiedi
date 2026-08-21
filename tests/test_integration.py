"""End-to-end, headless: a plan change surfaces in the companion.

Exercises the whole brain-free chain together — store (a real Voyage on disk) →
notices.transitions (Notices from the DAG diff) → the daemon's Notice(ssssss)
string-signal seam → companion reconstruction → presenter → render — with no bus and
no display (offscreen Qt). This is the seam that per-unit tests can't cover.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hiedi.core import notices, store  # noqa: E402
from hiedi.core.model import Chart, Leg, LegStatus, Waypoint  # noqa: E402
from hiedi.core.notices import NoticeKind  # noqa: E402
from hiedi.core.presence import Presence, PresenceLevel  # noqa: E402
from hiedi.core.presenter import Presentation  # noqa: E402
from hiedi.ui.companion import Companion, notice_from_signal  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _voyage_with_dependency(root):
    """A Voyage whose 'order' leg waits on 'measure' — persisted to disk."""
    vdir = store.create_voyage("Greenhouse", root=root, now=lambda: "2026-08-20")
    store.save_chart(vdir, Chart(
        waypoints=[Waypoint("w", "Site")],
        legs=[Leg("measure", "Measure the pad", waypoint="w"),
              Leg("order", "Order panels", waypoint="w", after=["measure"])]))
    return vdir


def _notices_from_completing_measure(vdir):
    """Snapshot, mark 'measure' done on disk, and diff → the emitted Notices."""
    before = store.load_chart(vdir, resolved=False)
    after = store.load_chart(vdir, resolved=False)
    after.leg("measure").status = LegStatus.DONE
    store.save_chart(vdir, after)
    return notices.transitions(before, after, vdir.path.name)


def _feed(companion, emitted):
    """Marshal each Notice through the string-signal seam and into the companion."""
    seen = []
    for n in emitted:
        args = (n.kind.value, n.voyage, n.title, n.body, n.leg or "", n.waypoint or "")
        seen.append(companion.handle_notice(notice_from_signal(*args)))
    return seen


def test_plan_change_bubbles_at_first_mate(app, tmp_path):
    vdir = _voyage_with_dependency(tmp_path / "Voyages")
    emitted = _notices_from_completing_measure(vdir)

    # the DAG diff produced exactly the "order is ready" event
    assert any(n.kind is NoticeKind.LEG_READY and n.leg == "order" for n in emitted)

    comp = Companion(Presence(level=PresenceLevel.FIRST_MATE, hourly_cap=5),
                     clock=lambda: 0.0)
    seen = _feed(comp, emitted)

    assert Presentation.BUBBLE in seen              # it surfaced as a bubble…
    assert "Order panels" in comp._bubble.text()    # …carrying the leg's title


def test_same_change_only_toasts_at_on_watch(app, tmp_path):
    vdir = _voyage_with_dependency(tmp_path / "Voyages")
    emitted = _notices_from_completing_measure(vdir)

    comp = Companion(Presence(level=PresenceLevel.ON_WATCH), clock=lambda: 0.0)
    seen = _feed(comp, emitted)

    # the quiet default tier never bubbles the same event
    assert Presentation.BUBBLE not in seen
    assert Presentation.TOAST in seen
