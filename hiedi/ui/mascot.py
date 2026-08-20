"""Hiedi's pose as a widget — the reusable presence surface.

Agent status maps to one of the canonical poses from the character bible
(idle/thinking/success/concern). If a labelled PNG exists under ``hiedi/data/mascot/``
it is shown; otherwise a tidy painted placeholder in Hiedi's teal is drawn so the app
is never empty before the art lands.

``MascotImage`` is the bare pose (a sized pixmap) — reused by the summon panel, the
companion, and (later) the floating companion / speech bubble. ``MascotWidget`` is
that image plus a status caption, as the summon panel uses it.
"""

from __future__ import annotations

from importlib import resources

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

# Hiedi palette (from the character bible).
TEAL = "#2f9f96"
GOLD = "#e6c66a"

_STATE_POSE = {
    "idle": ("listening", "⚓", "Ready when you are."),
    "thinking": ("thinking", "…", "Charting the route…"),
    "success": ("success", "✓", "Done — take a look."),
    "concern": ("concern", "!", "Hit a snag — see below."),
}


def _placeholder(pose: str, glyph: str, size: int = 120) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(TEAL))
    p.setPen(QColor(GOLD))
    p.drawEllipse(6, 6, size - 12, size - 12)
    p.setPen(QColor("#0c332e"))
    f = QFont()
    f.setPixelSize(int(size * 0.4))
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, glyph)
    p.end()
    return pm


def _load_pose(pose: str, size: int = 120) -> QPixmap:
    try:
        path = resources.files("hiedi.data").joinpath("mascot", f"{pose}.png")
        if path.is_file():
            pm = QPixmap(str(path))
            if not pm.isNull():
                return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        pass
    glyph = _STATE_POSE.get(pose, ("", "⚓", ""))[1]
    return _placeholder(pose, glyph, size)


def caption_for(state: str) -> str:
    """The status caption for an agent state (idle/thinking/success/concern)."""
    return _STATE_POSE.get(state, _STATE_POSE["idle"])[2]


class MascotImage(QLabel):
    """Just Hiedi's pose, at a fixed size — the reusable presence surface."""

    def __init__(self, size: int = 120, parent: QWidget | None = None) -> None:
        super().__init__(parent, alignment=Qt.AlignCenter)
        self._size = size
        self.set_status("idle")

    def set_status(self, state: str) -> None:
        pose = _STATE_POSE.get(state, _STATE_POSE["idle"])[0]
        self.setPixmap(_load_pose(pose, self._size))


class MascotWidget(QWidget):
    """The pose plus a status caption — as the summon panel shows it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._img = MascotImage(120)
        self._caption = QLabel(alignment=Qt.AlignCenter)
        self._caption.setWordWrap(True)
        self._caption.setStyleSheet("color: palette(mid);")
        lay = QVBoxLayout(self)
        lay.addWidget(self._img)
        lay.addWidget(self._caption)
        self.set_status("idle")

    def set_status(self, state: str) -> None:
        self._img.set_status(state)
        self._caption.setText(caption_for(state))


__all__ = ["MascotImage", "MascotWidget", "caption_for"]
