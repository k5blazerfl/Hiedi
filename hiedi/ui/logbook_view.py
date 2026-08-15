"""The Logbook view — the dated, attributed narrative, read-only.

Rendered newest-last (as stored) with attribution and any linked legs, so *who did what
and which brain* is always visible — the faithful contract made legible.
"""

from __future__ import annotations

from PySide6.QtWidgets import QTextBrowser

from ..core import logbook
from ..core.store import LoadedVoyage

_TYPE_COLOR = {
    "decision": "#54487A", "progress": "#2f9f96", "blocker": "#a9762a",
    "milestone": "#b5893a", "note": "#6b7280",
}


class LogbookView(QTextBrowser):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setOpenExternalLinks(False)

    def load(self, loaded: LoadedVoyage) -> None:
        rows = []
        for e in logbook.load(loaded.vdir):
            color = _TYPE_COLOR.get(e.type, "#6b7280")
            model = f" · model:{e.model}" if e.model else ""
            links = ("  " + " ".join(f"<code>[{l}]</code>" for l in e.legs)) if e.legs else ""
            rows.append(
                f'<p style="margin:2px 0"><span style="color:{color}"><b>{e.type}</b></span> '
                f'<small>· {e.date} · by:{e.by}{model}</small><br>'
                f'{_escape(e.body)}{links}</p>')
        self.setHtml("\n".join(rows) or "<p><i>The logbook is empty.</i></p>")


def _escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br>"))


__all__ = ["LogbookView"]
