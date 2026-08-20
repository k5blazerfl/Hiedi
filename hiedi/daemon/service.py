"""The ``org.hede.hiedi`` session service and its engine glue.

The D-Bus interface class is built inside :func:`build_interface` so importing this
module never requires ``dbus_next`` — only actually *running* the daemon does. Engine
calls (which may block on a model or a permission prompt) run in a thread-pool executor
so the asyncio loop keeps servicing the bus, including the ``RespondPermission`` call
that unblocks a prompt.

Interface (``org.hede.hiedi.Assistant``):

* methods: ``OpenVoyage(s)->s``, ``ListVoyages()->s``, ``DraftChart(s)->s``,
  ``ToggleLeg(ssb)``, ``Chat(ss)`` (JSON payloads), ``RespondPermission(ss)->b``,
  ``SweepNotices()->s`` (the periodic standing pass).
* signals: ``Status(s)`` (idle|thinking|success|concern), ``Token(s)`` (streamed),
  ``AskPermission(ssssbb)`` (request_id, tool, summary, detail, mutates, reversible),
  ``Notice(ssssss)`` (kind, voyage, title, body, leg, waypoint) — plan-state events.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from functools import partial

from .. import __version__
from ..core import store
from ..core.agent import AgentEngine
from ..core.agent.permissions import Decision
from ..core.brain import ClaudeBrain, OllamaBrain, Router
from ..core.model import Chart
from . import BUS_NAME, INTERFACE, OBJECT_PATH
from .bridge import PromptBridge
from .notice_bridge import NoticeBridge

_DECISIONS = {
    "deny": Decision.DENY,
    "allow_once": Decision.ALLOW_ONCE,
    "allow_session": Decision.ALLOW_SESSION,
}


def _chart_json(loaded: store.LoadedVoyage) -> dict:
    return {
        "voyage": loaded.voyage.to_dict(),
        "chart": loaded.chart.to_dict(),
        "config": loaded.config.to_dict(),
    }


def build_interface():
    """Construct the D-Bus ServiceInterface subclass (imports dbus_next lazily)."""
    from dbus_next.service import ServiceInterface, method, signal

    class HiediInterface(ServiceInterface):
        def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
            super().__init__(INTERFACE)
            self._loop = loop
            self._router = Router(OllamaBrain(), ClaudeBrain())
            self._bridge = PromptBridge(self._emit_ask)
            self._engine = AgentEngine(self._router, asker=self._bridge.asker)
            self._notices = NoticeBridge(self._emit_notice)

        # -- signal plumbing -------------------------------------------------

        def _emit_ask(self, request_id: str, req) -> None:
            # Called from the engine's worker thread → hop back to the loop thread.
            self._loop.call_soon_threadsafe(
                self.AskPermission, request_id, req.tool, req.summary,
                req.detail, req.mutates, req.reversible)

        def _emit_notice(self, kind: str, voyage: str, title: str,
                         body: str, leg: str, waypoint: str) -> None:
            # The NoticeBridge may run on the loop thread or a worker; hop uniformly.
            self._loop.call_soon_threadsafe(
                self.Notice, kind, voyage, title, body, leg, waypoint)

        def _set_status(self, state: str) -> None:
            self._loop.call_soon_threadsafe(self.Status, state)

        async def _run(self, fn, *args):
            """Run a blocking engine call in the executor, bracketed by status."""
            self.Status("thinking")
            try:
                result = await self._loop.run_in_executor(None, partial(fn, *args))
                self._set_status("success")
                return result
            except Exception:
                self._set_status("concern")
                raise

        # -- methods ---------------------------------------------------------

        @method()
        def Version(self) -> "s":  # noqa: F821
            return __version__

        @method()
        def ListVoyages(self) -> "s":  # noqa: F821
            out = []
            for d in store.list_voyages():
                v = store.load_voyage(d)
                out.append({"slug": d.path.name, "title": v.title, "status": v.status.value})
            return json.dumps(out)

        @method()
        def OpenVoyage(self, ref: "s") -> "s":  # noqa: F821
            loaded = store.find_voyage(ref)
            self._notices.on_open(loaded)          # surface this Voyage's standing notices
            return json.dumps(_chart_json(loaded))

        @method()
        async def DraftChart(self, ref: "s") -> "s":  # noqa: F821
            loaded = store.find_voyage(ref)
            before = Chart.from_dict(loaded.chart.to_dict())   # snapshot before the mutation
            res = await self._run(self._engine.draft_chart, loaded)
            if res.applied:
                self._notices.on_mutation(before, loaded.chart, loaded.voyage.id)
            return json.dumps({
                "applied": res.applied, "message": res.message,
                "brain": res.decision.brain, "model": res.decision.model,
                "milestones": res.milestones,
                "chart": _chart_json(loaded) if res.applied else None,
            })

        @method()
        async def ToggleLeg(self, ref: "s", leg: "s", done: "b") -> "s":  # noqa: F821
            loaded = store.find_voyage(ref)
            before = Chart.from_dict(loaded.chart.to_dict())   # snapshot before the mutation
            res = await self._run(partial(self._engine.toggle_leg, loaded, leg, done=done))
            if res.applied:
                self._notices.on_mutation(before, loaded.chart, loaded.voyage.id)
            return json.dumps({
                "applied": res.applied, "message": res.message,
                "milestones": res.milestones,
                "chart": _chart_json(loaded) if res.applied else None,
            })

        @method()
        async def Chat(self, ref: "s", text: "s") -> "s":  # noqa: F821
            loaded = store.find_voyage(ref)
            reply, decision = await self._run(partial(self._engine.chat, loaded, text))
            return json.dumps({"content": reply.content, "brain": decision.brain,
                               "model": decision.model, "reason": decision.reason})

        @method()
        def RespondPermission(self, request_id: "s", decision: "s") -> "b":  # noqa: F821
            d = _DECISIONS.get(decision, Decision.DENY)
            return self._bridge.respond(request_id, d)

        @method()
        def SweepNotices(self) -> "s":  # noqa: F821
            # The periodic standing pass (drift/long-lead) across all Voyages; a
            # client (or a future timer) drives cadence. De-dup lives in the bridge.
            return json.dumps({"emitted": self._notices.sweep()})

        # -- signals ---------------------------------------------------------

        @signal()
        def Status(self, state: "s") -> "s":  # noqa: F821
            return state

        @signal()
        def Token(self, text: "s") -> "s":  # noqa: F821
            return text

        @signal()
        def AskPermission(self, request_id: "s", tool: "s", summary: "s",  # noqa: F821
                          detail: "s", mutates: "b", reversible: "b") -> "ssssbb":  # noqa: F821
            return [request_id, tool, summary, detail, mutates, reversible]

        @signal()
        def Notice(self, kind: "s", voyage: "s", title: "s",  # noqa: F821
                   body: "s", leg: "s", waypoint: "s") -> "ssssss":  # noqa: F821
            # A plan-state event worth surfacing (Voyage-only for v1). leg/waypoint
            # are "" when not applicable. See hiedi.core.notices.
            return [kind, voyage, title, body, leg, waypoint]

    return HiediInterface


async def _serve() -> None:
    from dbus_next import BusType
    from dbus_next.aio import MessageBus

    loop = asyncio.get_running_loop()
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    iface = build_interface()(loop)
    bus.export(OBJECT_PATH, iface)
    await bus.request_name(BUS_NAME)
    print(f"hiedid {__version__} — serving {BUS_NAME} on the session bus")
    await asyncio.get_event_loop().create_future()  # run forever


def run() -> int:
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        print("\nhiedid: shutting down")
    except ImportError as e:
        print(f"hiedid needs the daemon extra: pip install 'hiedi[daemon]' ({e})")
        return 1
    return 0


__all__ = ["build_interface", "run"]
