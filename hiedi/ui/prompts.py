"""The permission dialog — the visible face of the faithful contract.

Shown when a tool's policy is ``ask``. Offers the three-way decision the broker
understands (allow once / allow for this Voyage / deny) and makes the stakes clear:
whether the action mutates files and whether it can be undone.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout

from ..core.agent.permissions import Decision, ToolRequest


class PermissionDialog(QDialog):
    def __init__(self, request: ToolRequest, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Hiedi asks permission")
        self._decision = Decision.DENY

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>Hiedi wants to:</b><br>{request.summary}"))
        rev = "This can be undone." if request.reversible else "⚠ This cannot be undone."
        kind = "Changes your files." if request.mutates else "Reads only."
        meta = QLabel(f"<small>{kind} {rev}<br>tool: <code>{request.tool}</code></small>")
        lay.addWidget(meta)
        if request.detail:
            d = QLabel(request.detail)
            d.setWordWrap(True)
            lay.addWidget(d)

        box = QDialogButtonBox()
        once = box.addButton("Allow once", QDialogButtonBox.AcceptRole)
        session = box.addButton("Allow this Voyage", QDialogButtonBox.AcceptRole)
        deny = box.addButton("Deny", QDialogButtonBox.RejectRole)
        deny.setDefault(True)
        once.clicked.connect(lambda: self._choose(Decision.ALLOW_ONCE))
        session.clicked.connect(lambda: self._choose(Decision.ALLOW_SESSION))
        deny.clicked.connect(lambda: self._choose(Decision.DENY))
        lay.addWidget(box)

    def _choose(self, decision: Decision) -> None:
        self._decision = decision
        self.accept() if decision is not Decision.DENY else self.reject()

    @property
    def decision(self) -> Decision:
        return self._decision

    @staticmethod
    def ask(request: ToolRequest, parent=None) -> Decision:
        dlg = PermissionDialog(request, parent)
        dlg.exec()
        return dlg.decision


__all__ = ["PermissionDialog"]
