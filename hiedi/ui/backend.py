"""The UI's view of the engine — an abstract backend + an in-process implementation.

Keeping the widgets behind :class:`Backend` means the MVP can run the engine directly
(no bus) while a future ``DBusBackend`` (talking to ``hiedid``) can replace it without
touching a single widget. The in-process backend runs blocking engine verbs on a
:class:`QThread` worker and routes permission asks through a :class:`PromptBridge` whose
``on_ask`` emits a Qt signal — so the ask surfaces as a GUI-thread dialog while the
worker thread blocks for the answer.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal

from ..core import store
from ..core.agent import AgentEngine
from ..core.agent.permissions import Decision, ToolRequest
from ..core.brain import ClaudeBrain, OllamaBrain, Router
from ..daemon.bridge import PromptBridge


class _Worker(QThread):
    """Runs one engine call off the GUI thread; emits the result or an error."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:  # pragma: no cover - exercised via the app, not unit tests
        try:
            self.done.emit(self._fn())
        except Exception as e:  # surface, don't crash the app
            self.failed.emit(f"{type(e).__name__}: {e}")


class Backend(QObject):
    """UI-facing contract. Signals are what widgets bind to."""

    # request_id, ToolRequest — GUI shows a dialog, then calls respond()
    ask_permission = Signal(str, object)
    status = Signal(str)          # idle | thinking | success | concern
    result = Signal(object)       # verb result (DraftResult / TurnResult / Reply tuple)
    error = Signal(str)

    def respond(self, request_id: str, decision: Decision) -> None: ...
    def open_voyage(self, ref: str) -> store.LoadedVoyage: ...
    def draft_chart(self, loaded: store.LoadedVoyage) -> None: ...
    def toggle_leg(self, loaded: store.LoadedVoyage, leg_id: str, done: bool) -> None: ...


class InProcessBackend(Backend):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._router = Router(OllamaBrain(), ClaudeBrain())
        self._bridge = PromptBridge(self._on_ask)
        self._engine = AgentEngine(self._router, asker=self._bridge.asker)
        self._worker: _Worker | None = None

    def _on_ask(self, request_id: str, req: ToolRequest) -> None:
        # Called from the worker thread; the queued connection hops to the GUI thread.
        self.ask_permission.emit(request_id, req)

    def respond(self, request_id: str, decision: Decision) -> None:
        self._bridge.respond(request_id, decision)

    def open_voyage(self, ref: str) -> store.LoadedVoyage:
        return store.find_voyage(ref)

    def _run(self, fn: Callable[[], object]) -> None:
        self.status.emit("thinking")
        worker = _Worker(fn)
        worker.done.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _on_done(self, result: object) -> None:
        self.status.emit("success")
        self.result.emit(result)

    def _on_failed(self, msg: str) -> None:
        self.status.emit("concern")
        self.error.emit(msg)

    def draft_chart(self, loaded: store.LoadedVoyage) -> None:
        self._run(lambda: self._engine.draft_chart(loaded))

    def toggle_leg(self, loaded: store.LoadedVoyage, leg_id: str, done: bool) -> None:
        self._run(lambda: self._engine.toggle_leg(loaded, leg_id, done=done))


__all__ = ["Backend", "InProcessBackend"]
