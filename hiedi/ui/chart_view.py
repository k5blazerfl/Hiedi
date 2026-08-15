"""The Chart view — waypoints as groups, legs as checkable items.

Checking a leg emits :attr:`toggled` ``(leg_id, done)``; the app routes that through the
backend (and thus the permission gate). Ready/blocked/done state is shown as a glyph so
the DAG is legible at a glance; blocked legs are dimmed and not checkable.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from ..core.model import Chart, LegStatus

_GLYPH = {
    "done": "✓", "ready": "○", "blocked": "×",
    "active": "▸", "dropped": "–", "todo": "·",
}


class ChartView(QTreeWidget):
    toggled = Signal(str, bool)   # leg_id, done

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self._loading = False
        self.itemChanged.connect(self._on_item_changed)

    def load(self, chart: Chart) -> None:
        self._loading = True
        self.clear()
        seen: set[str] = set()
        for wp in chart.waypoints:
            group = QTreeWidgetItem(self, [f"⚓ {wp.title}"])
            group.setFlags(group.flags() & ~Qt.ItemIsUserCheckable)
            group.setExpanded(True)
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            for leg in [l for l in chart.legs if l.waypoint == wp.id]:
                self._add_leg(group, leg)
                seen.add(leg.id)
        loose = [l for l in chart.legs if l.id not in seen]
        if loose:
            group = QTreeWidgetItem(self, ["(unassigned)"])
            group.setExpanded(True)
            for leg in loose:
                self._add_leg(group, leg)
        self._loading = False

    def _add_leg(self, parent: QTreeWidgetItem, leg) -> None:
        status = leg.status.value
        item = QTreeWidgetItem(parent, [f"{_GLYPH.get(status, '·')} {leg.title}"])
        item.setData(0, Qt.UserRole, leg.id)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked if leg.status is LegStatus.DONE else Qt.Unchecked)
        if leg.status is LegStatus.BLOCKED:
            item.setForeground(0, self.palette().mid())
            item.setToolTip(0, "Blocked — an upstream Leg isn't done yet.")
        if leg.by:
            tip = item.toolTip(0)
            item.setToolTip(0, (tip + "\n" if tip else "") + f"drafted by:{leg.by}"
                            + (f" ({leg.model})" if leg.model else ""))

    def _on_item_changed(self, item: QTreeWidgetItem, _col: int) -> None:
        if self._loading:
            return
        leg_id = item.data(0, Qt.UserRole)
        if not leg_id:
            return
        self.toggled.emit(leg_id, item.checkState(0) == Qt.Checked)


__all__ = ["ChartView"]
