"""``hiedi`` — the summon panel main window.

Layout: Hiedi's mascot + status on the left; the Chart in the centre; the Logbook and a
compose box on the right. A toolbar picks/creates a Voyage and triggers a draft. Every
mutation goes through the backend's permission gate, so the dialog from
:mod:`hiedi.ui.prompts` is the app's conscience.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..core import store
from ..core.agent.permissions import Decision, ToolRequest
from .backend import Backend, InProcessBackend
from .chart_view import ChartView
from .logbook_view import LogbookView
from .mascot import MascotWidget
from .prompts import PermissionDialog


class SummonPanel(QMainWindow):
    def __init__(self, backend: Backend | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Hiedi")
        self.resize(940, 600)
        self.backend = backend or InProcessBackend(self)
        self._loaded: store.LoadedVoyage | None = None

        self._build_ui()
        self._wire_backend()
        self.refresh_voyage_list()

    # -- construction ------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # toolbar row
        bar = QHBoxLayout()
        self.voyage_combo = QComboBox()
        self.voyage_combo.currentIndexChanged.connect(self._on_voyage_selected)
        new_btn = QPushButton("New Voyage…")
        new_btn.clicked.connect(self._new_voyage)
        self.draft_btn = QPushButton("Draft Chart")
        self.draft_btn.clicked.connect(self._draft)
        self.draft_btn.setEnabled(False)
        self.brain_lbl = QLabel("")
        self.brain_lbl.setStyleSheet("color: palette(mid);")
        bar.addWidget(QLabel("Voyage:"))
        bar.addWidget(self.voyage_combo, 1)
        bar.addWidget(new_btn)
        bar.addWidget(self.draft_btn)
        bar.addWidget(self.brain_lbl)
        root.addLayout(bar)

        # main split: mascot | chart | logbook+compose
        split = QSplitter(Qt.Horizontal)

        left = QWidget()
        lv = QVBoxLayout(left)
        self.mascot = MascotWidget()
        lv.addWidget(self.mascot)
        lv.addStretch(1)
        split.addWidget(left)

        self.chart = ChartView()
        self.chart.toggled.connect(self._toggle_leg)
        split.addWidget(self.chart)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.addWidget(QLabel("<b>Logbook</b>"))
        self.logbook = LogbookView()
        rv.addWidget(self.logbook, 1)
        compose_row = QHBoxLayout()
        self.compose = QLineEdit()
        self.compose.setPlaceholderText("Ask Hiedi… (⏎)")
        self.compose.returnPressed.connect(self._send)
        compose_row.addWidget(self.compose, 1)
        rv.addLayout(compose_row)
        split.addWidget(right)

        split.setSizes([200, 420, 320])
        root.addWidget(split, 1)
        self.statusBar().showMessage("Ready when you are.")

    def _wire_backend(self) -> None:
        # Queued automatically: emitted from the worker thread, slot lives on the GUI thread.
        self.backend.ask_permission.connect(self._on_ask)
        self.backend.status.connect(self.mascot.set_status)
        self.backend.result.connect(self._on_result)
        self.backend.error.connect(self._on_error)

    # -- voyage selection --------------------------------------------------------

    def refresh_voyage_list(self) -> None:
        self.voyage_combo.blockSignals(True)
        self.voyage_combo.clear()
        for d in store.list_voyages():
            v = store.load_voyage(d)
            self.voyage_combo.addItem(f"{v.title}", d.path.name)
        self.voyage_combo.blockSignals(False)
        if self.voyage_combo.count():
            self._on_voyage_selected(self.voyage_combo.currentIndex())

    def _on_voyage_selected(self, index: int) -> None:
        slug = self.voyage_combo.itemData(index)
        if not slug:
            return
        self._load(slug)

    def _load(self, ref: str) -> None:
        self._loaded = self.backend.open_voyage(ref)
        self.draft_btn.setEnabled(True)
        self.brain_lbl.setText(f"brain: {self._loaded.config.routing.default}")
        self._refresh_views()

    def _refresh_views(self) -> None:
        if not self._loaded:
            return
        self.chart.load(self._loaded.chart)
        self.logbook.load(self._loaded)

    # -- actions -----------------------------------------------------------------

    def _new_voyage(self) -> None:
        title, ok = QInputDialog.getText(self, "New Voyage", "What are we building? (goal)")
        if not ok or not title.strip():
            return
        try:
            vdir = store.create_voyage(title.strip())
        except FileExistsError:
            self.statusBar().showMessage("A Voyage with that name already exists.")
            return
        self.refresh_voyage_list()
        idx = self.voyage_combo.findData(vdir.path.name)
        if idx >= 0:
            self.voyage_combo.setCurrentIndex(idx)

    def _draft(self) -> None:
        if self._loaded:
            self.statusBar().showMessage("Hiedi is charting the route…")
            self.backend.draft_chart(self._loaded)

    def _toggle_leg(self, leg_id: str, done: bool) -> None:
        if self._loaded:
            self.backend.toggle_leg(self._loaded, leg_id, done)

    def _send(self) -> None:
        text = self.compose.text().strip()
        if not text or not self._loaded:
            return
        self.compose.clear()
        # MVP: the compose box triggers a fresh draft when empty-plan; otherwise it's a
        # placeholder for conversational editing (wired next). Keep it honest for now.
        self.statusBar().showMessage(f"(chat coming next) — you said: {text}")

    # -- backend signals ---------------------------------------------------------

    def _on_ask(self, request_id: str, request: ToolRequest) -> None:
        decision = PermissionDialog.ask(request, self)
        self.backend.respond(request_id, decision)

    def _on_result(self, result: object) -> None:
        msg = getattr(result, "message", "Done.")
        milestones = getattr(result, "milestones", None)
        if milestones:
            msg += f"  ⚓ reached: {', '.join(milestones)}"
        decision = getattr(result, "decision", None)
        if decision is not None:
            self.brain_lbl.setText(f"brain: {decision.brain} ({decision.model})")
        self.statusBar().showMessage(msg)
        if self._loaded:                       # reload from disk — single source of truth
            self._loaded = self.backend.open_voyage(self._loaded.vdir.path.name)
            self._refresh_views()

    def _on_error(self, msg: str) -> None:
        self.statusBar().showMessage(f"Snag: {msg}")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("hiedi")
    win = SummonPanel()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
