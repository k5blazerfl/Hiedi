"""The agent engine — the loop that turns a brain reply into gated, attributed effects.

The engine owns *no* IO of its own: brain calls go through the :class:`~hiedi.core.brain.router.Router`,
and every mutation goes through a :class:`~hiedi.core.agent.tools.Tool` gated by a
:class:`~hiedi.core.agent.permissions.PermissionBroker`. So there is exactly one place a
write can happen, and it is always attributed and (where possible) reversible.

MVP verbs:

* :meth:`draft_chart` — ask the brain to draft a Chart, then apply it via ``write_chart``
  (which prompts if the policy says ``ask``), and log a ``progress`` entry.
* :meth:`toggle_leg` — mark a Leg done/not-done, re-resolve the DAG, and auto-log a
  ``milestone`` when a Waypoint's legs all complete.
* :meth:`chat` — a read-only conversational turn (routes a brain reply; writes nothing).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import logbook
from ..brain.base import Message, Reply
from ..brain.router import Router, RoutingDecision
from ..model import Chart, LegStatus
from ..store import Clock, LoadedVoyage, load_chart, today
from . import prompts
from .permissions import Asker, Grant, PermissionBroker, PermissionDenied, ToolRequest, deny_all
from .tools import ToolContext, ToolResult, get_tool


@dataclass
class DraftResult:
    chart: Chart | None
    decision: RoutingDecision
    reply: Reply
    applied: bool
    grant: Grant | None = None
    milestones: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class TurnResult:
    applied: bool
    grant: Grant | None = None
    milestones: list[str] = field(default_factory=list)
    undo: object = None          # Callable | None — reverse the mutation
    message: str = ""


class AgentEngine:
    def __init__(self, router: Router, *, asker: Asker = deny_all, now: Clock = today) -> None:
        self.router = router
        self.asker = asker
        self.now = now

    # -- helpers -----------------------------------------------------------------

    def broker(self, loaded: LoadedVoyage) -> PermissionBroker:
        return PermissionBroker(loaded.config, asker=self.asker)

    def _ctx(self, loaded: LoadedVoyage, model: str | None) -> ToolContext:
        return ToolContext(loaded=loaded, by="hiedi", model=model, now=self.now)

    def _call(self, broker: PermissionBroker, ctx: ToolContext, name: str, args: dict) -> tuple[Grant, ToolResult | None]:
        """Gate a tool call, then run it if allowed. Returns (grant, result|None)."""
        tool = get_tool(name)
        request = ToolRequest(
            tool=name, summary=tool.summarize(args),
            mutates=tool.mutates, reversible=tool.reversible,
        )
        grant = broker.check(request)
        if not grant.allowed:
            return grant, None
        return grant, tool.run(ctx, args)

    def _apply_chart(
        self, broker: PermissionBroker, ctx: ToolContext, new_chart: Chart,
    ) -> tuple[Grant, ToolResult | None, list[str]]:
        """Apply a chart via the gated write_chart tool + auto-log milestones."""
        before = load_chart(ctx.loaded.vdir)  # resolved snapshot for the milestone diff
        grant, result = self._call(broker, ctx, "write_chart", {"chart": new_chart})
        if result is None:
            return grant, None, []
        after = ctx.loaded.chart  # write_chart refreshed this to the resolved view
        milestones = logbook.newly_completed_waypoints(before, after)
        for wid in milestones:
            wp = next((w for w in after.waypoints if w.id == wid), None)
            self._call(broker, ctx, "write_logbook", {
                "type": "milestone",
                "body": f"Waypoint reached: {wp.title if wp else wid}.",
                "by": "hiedi", "model": ctx.model, "legs": [],
            })
        return grant, result, milestones

    # -- verbs -------------------------------------------------------------------

    def draft_chart(
        self, loaded: LoadedVoyage, *,
        want_cloud: bool = False, consented: bool = False, temperature: float = 0.5,
    ) -> DraftResult:
        messages = prompts.draft_chart_messages(loaded.voyage)
        reply, decision = self.router.chat(
            loaded.config, messages,
            want_cloud=want_cloud, consented=consented, temperature=temperature)

        try:
            chart = prompts.parse_chart(reply.content, by="hiedi", model=reply.model)
        except ValueError as e:
            return DraftResult(None, decision, reply, applied=False,
                               message=f"couldn't parse a Chart from the reply: {e}")

        ctx = self._ctx(loaded, reply.model)
        broker = self.broker(loaded)
        grant, result, milestones = self._apply_chart(broker, ctx, chart)
        if result is None:
            return DraftResult(chart, decision, reply, applied=False, grant=grant,
                               message="draft ready, but applying the Chart was not approved")

        # A progress entry, attributed — Hiedi announcing what it did.
        self._call(broker, ctx, "write_logbook", {
            "type": "progress",
            "body": (f"Drafted the initial Chart: {len(chart.waypoints)} waypoint(s), "
                     f"{len(chart.legs)} leg(s). Ready for your review."),
            "by": "hiedi", "model": reply.model,
        })
        return DraftResult(loaded.chart, decision, reply, applied=True, grant=grant,
                           milestones=milestones, message="Chart drafted and applied.")

    def toggle_leg(self, loaded: LoadedVoyage, leg_id: str, *, done: bool) -> TurnResult:
        chart = load_chart(loaded.vdir)
        leg = chart.leg(leg_id)
        if leg is None:
            return TurnResult(applied=False, message=f"no such leg '{leg_id}'")
        # DONE is explicit; clearing drops to TODO and lets the resolver recompute.
        leg.status = LegStatus.DONE if done else LegStatus.TODO

        ctx = self._ctx(loaded, model=None)
        broker = self.broker(loaded)
        grant, result, milestones = self._apply_chart(broker, ctx, chart)
        if result is None:
            return TurnResult(applied=False, grant=grant,
                              message="marking the leg was not approved")
        verb = "done" if done else "reopened"
        return TurnResult(applied=True, grant=grant, milestones=milestones,
                          undo=result.undo, message=f"Leg '{leg_id}' marked {verb}.")

    def chat(
        self, loaded: LoadedVoyage, text: str, *,
        history: list[Message] | None = None,
        want_cloud: bool = False, consented: bool = False, temperature: float = 0.7,
    ) -> tuple[Reply, RoutingDecision]:
        """A read-only conversational turn. Writes nothing — use the verbs for that."""
        messages = [Message("system", prompts.persona())]
        messages += history or []
        messages.append(Message("user", text))
        return self.router.chat(
            loaded.config, messages,
            want_cloud=want_cloud, consented=consented, temperature=temperature)


__all__ = ["AgentEngine", "DraftResult", "TurnResult"]
