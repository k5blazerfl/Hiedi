"""The async↔sync bridge for permission prompts.

The agent engine calls its ``asker`` synchronously (it runs in a worker thread), but the
answer arrives asynchronously over the bus (the UI calls ``RespondPermission`` later).
:class:`PromptBridge` reconciles the two and is deliberately **bus-free and UI-free** so
it can be unit-tested on its own:

* :meth:`asker` is handed to the engine. It registers a pending prompt, fires the
  injected ``on_ask`` (the service wires this to emit a D-Bus signal), then blocks on a
  :class:`threading.Event` until :meth:`respond` supplies a decision — or a timeout,
  which **fails closed** (DENY).
* :meth:`respond` is called from the bus thread to resolve a pending prompt.

This is the same fail-closed default as the core broker: no answer ⇒ no action.
"""

from __future__ import annotations

import itertools
import threading
from collections.abc import Callable
from dataclasses import dataclass

from ..core.agent.permissions import Decision, ToolRequest


@dataclass
class _Pending:
    request: ToolRequest
    event: threading.Event
    decision: Decision = Decision.DENY


# on_ask(request_id, request) -> None  (e.g. emit an AskPermission signal)
OnAsk = Callable[[str, ToolRequest], None]


class PromptBridge:
    def __init__(self, on_ask: OnAsk, *, timeout: float = 300.0) -> None:
        self._on_ask = on_ask
        self._timeout = timeout
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.Lock()
        self._ids = itertools.count(1)

    def asker(self, request: ToolRequest) -> Decision:
        """The blocking asker handed to the engine (runs in a worker thread)."""
        rid = str(next(self._ids))
        pending = _Pending(request=request, event=threading.Event())
        with self._lock:
            self._pending[rid] = pending
        try:
            self._on_ask(rid, request)
        except Exception:
            # If we can't even deliver the prompt, fail closed immediately.
            with self._lock:
                self._pending.pop(rid, None)
            return Decision.DENY
        answered = pending.event.wait(self._timeout)
        with self._lock:
            self._pending.pop(rid, None)
        return pending.decision if answered else Decision.DENY

    def respond(self, request_id: str, decision: Decision) -> bool:
        """Resolve a pending prompt. Returns False if the id is unknown/expired."""
        with self._lock:
            pending = self._pending.get(request_id)
        if pending is None:
            return False
        pending.decision = decision
        pending.event.set()
        return True

    def pending_ids(self) -> list[str]:
        with self._lock:
            return list(self._pending)


__all__ = ["PromptBridge", "OnAsk"]
