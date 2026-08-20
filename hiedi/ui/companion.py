"""``hiedi-companion`` — the standalone desktop companion.

A small always-present PySide6 surface that reflects Hiedi's live status in her
pose and turns incoming Notices into the right presentation (toast / pose / bubble)
per the presence tier and the interruption budget. Standalone it is its own window;
once HeDE's panel publishes the applet-slot contract, the **native panel** renders
the bar pin and drives this process over D-Bus (``org.hede.hiedi``) — PySide6 stays
in the Hiedi world and never enters the always-on shell path.

The rendering logic lives in :mod:`hiedi.core.presenter` (pure, tested); this module
is the Qt shell around it. See ``docs/desktop-assistant.md``.
"""

from __future__ import annotations

import sys
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..core import presence as presence_mod
from ..core.budget import InterruptionBudget
from ..core.presence import Presence, PresenceLevel
from ..core.presenter import Presentation, decide
from .mascot import MascotImage

_LEVELS = [
    (PresenceLevel.ON_WATCH, "On Watch"),
    (PresenceLevel.ON_DECK, "On Deck"),
    (PresenceLevel.AT_YOUR_SIDE, "At Your Side"),
    (PresenceLevel.FIRST_MATE, "First Mate"),
]


class Companion(QWidget):
    """The companion surface: mascot + presence dial, rendering Notices."""

    def __init__(self, presence: Presence | None = None, *,
                 clock=time.monotonic, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Hiedi")
        self._presence = presence or presence_mod.load()
        self._budget = InterruptionBudget(self._presence)
        self._clock = clock

        self._mascot = MascotImage(96)

        self._bubble = QLabel(alignment=Qt.AlignCenter)
        self._bubble.setObjectName("HiediBubble")
        self._bubble.setWordWrap(True)
        self._bubble.setVisible(False)
        self._bubble.setStyleSheet(
            "QLabel#HiediBubble { background: palette(base); border: 1px solid palette(mid);"
            " border-radius: 8px; padding: 6px 10px; }")
        self._hideTimer = QTimer(self)
        self._hideTimer.setSingleShot(True)
        self._hideTimer.timeout.connect(lambda: self._bubble.setVisible(False))

        self._dial = QComboBox()
        for lvl, label in _LEVELS:
            self._dial.addItem(label, int(lvl))
        self._dial.setCurrentIndex(int(self._presence.level))
        self._dial.currentIndexChanged.connect(self._on_dial)

        lay = QVBoxLayout(self)
        lay.addWidget(self._mascot)
        lay.addWidget(self._bubble)
        row = QHBoxLayout()
        row.addWidget(QLabel("Presence:"))
        row.addWidget(self._dial, 1)
        lay.addLayout(row)

    # -- inputs from the daemon (org.hede.hiedi signals) -----------------------

    def set_status(self, state: str) -> None:
        """Reflect the daemon's Status signal in the pose."""
        self._mascot.set_status(state)

    def handle_notice(self, notice, *, focus_ok: bool = True) -> Presentation:
        """Present a Notice per tier + budget; returns the chosen presentation."""
        p = decide(notice, self._presence, self._budget,
                   now=self._clock(), focus_ok=focus_ok)
        if p is Presentation.BUBBLE:
            self._flash(notice, ttl_ms=8000)
        elif p is Presentation.TOAST:
            self._flash(notice, ttl_ms=5000)
        elif p is Presentation.POSE:
            # ambient / DND: reflect it in the pose, don't interrupt
            self._mascot.set_status("concern" if notice.severity >= 3 else "success")
        # Presentation.NONE → silent
        return p

    def _flash(self, notice, *, ttl_ms: int) -> None:
        text = notice.title if not notice.body else f"{notice.title}\n{notice.body}"
        self._bubble.setText(text)
        self._bubble.setVisible(True)
        self._hideTimer.start(ttl_ms)

    # -- presence dial ---------------------------------------------------------

    def presence(self) -> Presence:
        return self._presence

    def set_level(self, level) -> None:
        """Set the presence tier (updates the dial, which persists it)."""
        self._dial.setCurrentIndex(int(PresenceLevel(level)))

    def _on_dial(self, index: int) -> None:
        self._presence.level = PresenceLevel(self._dial.itemData(index))
        presence_mod.save(self._presence)


def _demo(companion: Companion) -> None:
    """Feed a couple of sample Notices so the companion is visible when run live."""
    from ..core.notices import Notice, NoticeKind
    companion.set_status("success")
    QTimer.singleShot(800, lambda: companion.handle_notice(
        Notice(NoticeKind.LEG_READY, "demo", "Ready to start: Pour the footings",
               "Its prerequisites are done.")))


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("hiedi-companion")
    companion = Companion()
    # Live bus wiring (org.hede.hiedi Status/Notice via dbus_next) lands with the
    # panel applet-slot contract + a display session; standalone runs without it.
    if "--demo" in sys.argv:
        _demo(companion)
    companion.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
