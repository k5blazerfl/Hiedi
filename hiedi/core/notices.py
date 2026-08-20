"""Plan-state Notices — the events Hiedi may surface about a Voyage.

Everything here is computed from the pure data model (the Chart DAG + logbook
dates), so the entire steady-state notification value works with **no AI and no
bus**. This module only *computes candidate notices*; the presentation layer
(presence tier, per-kind mutes, the interruption budget) gates them elsewhere.

Scope is deliberately **Voyage-only** for v1 (design: ``docs/desktop-assistant.md``
§6) — Hiedi speaks for plans, not the desktop at large. New kinds register here, so
widening to system-wide later is additive.

Two families:

* **Transitions** — computed by diffing a *before* and *after* Chart (leg became
  ready, leg became blocked, waypoint reached). Mirrors
  :func:`hiedi.core.logbook.newly_completed_waypoints`.
* **Standing** — computed from one Voyage's current state + a clock (drift on a
  quiet active Voyage; a long-lead ``needs`` item whose waypoint ``target`` is near;
  arrival). Clock-injectable so tests are deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

from . import logbook
from .model import Chart, Leg, LegStatus, VoyageStatus
from .store import Clock, LoadedVoyage, resolve, today


class NoticeKind(str, Enum):
    LEG_READY = "leg_ready"
    WAYPOINT_REACHED = "waypoint_reached"
    BLOCKER = "blocker"
    LONG_LEAD = "long_lead"
    DRIFT = "drift"
    ARRIVAL = "arrival"


# Rough loudness ordering, for the interruption budget's severity gate.
_SEVERITY: dict[NoticeKind, int] = {
    NoticeKind.BLOCKER: 3,
    NoticeKind.LONG_LEAD: 3,
    NoticeKind.ARRIVAL: 2,
    NoticeKind.WAYPOINT_REACHED: 2,
    NoticeKind.LEG_READY: 1,
    NoticeKind.DRIFT: 1,
}


@dataclass
class Notice:
    """One thing worth surfacing, about one Voyage. Plain data — bus-serializable."""

    kind: NoticeKind
    voyage: str                    # voyage id
    title: str
    body: str = ""
    leg: str | None = None
    waypoint: str | None = None

    @property
    def severity(self) -> int:
        return _SEVERITY.get(self.kind, 1)

    def key(self) -> str:
        """Stable identity so the same event isn't surfaced twice."""
        anchor = self.leg or self.waypoint or ""
        return f"{self.voyage}:{self.kind.value}:{anchor}"

    def to_dict(self) -> dict[str, Any]:
        d = {
            "kind": self.kind.value, "voyage": self.voyage, "title": self.title,
            "body": self.body, "leg": self.leg, "waypoint": self.waypoint,
        }
        return {k: v for k, v in d.items() if v not in (None, "")}


# --------------------------------------------------------------------------- helpers


def _flat(chart: Chart) -> dict[str, Leg]:
    out: dict[str, Leg] = {}
    def walk(legs: list[Leg]) -> None:
        for leg in legs:
            out[leg.id] = leg
            walk(leg.sub)
    walk(chart.legs)
    return out


def _valid_date(s: Any) -> bool:
    if not isinstance(s, str):
        return False
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def _need_label(need: Any) -> str:
    """A ``needs`` item is freeform or ``{item, qty, have}`` — render it briefly."""
    if isinstance(need, dict):
        return str(need.get("item", need))
    return str(need)


# ----------------------------------------------------------------------- transitions


def transitions(before: Chart, after: Chart, voyage_id: str) -> list[Notice]:
    """Notices for what changed between two Charts (leg ready/blocked, waypoint met).

    ``before``/``after`` are the authored charts; the DAG is resolved here so the
    caller need not pre-resolve. New legs (absent in ``before``) can raise
    ``leg_ready`` but never ``blocked`` — a freshly-added blocked leg isn't news.
    """
    rb = resolve(before)
    ra = resolve(after)
    fa = _flat(after)
    out: list[Notice] = []

    for lid, leg in fa.items():
        was = rb.get(lid)
        now_status = ra.get(lid)
        if now_status == was:
            continue
        if now_status is LegStatus.READY and was is not LegStatus.READY:
            out.append(Notice(
                NoticeKind.LEG_READY, voyage_id,
                title=f"Ready to start: {leg.title}",
                body="Its prerequisites are done.",
                leg=lid, waypoint=leg.waypoint))
        elif now_status is LegStatus.BLOCKED and was not in (None, LegStatus.BLOCKED):
            out.append(Notice(
                NoticeKind.BLOCKER, voyage_id,
                title=f"Blocked: {leg.title}",
                body="A prerequisite is no longer done.",
                leg=lid, waypoint=leg.waypoint))

    for wid in logbook.newly_completed_waypoints(before, after):
        wp = next((w for w in after.waypoints if w.id == wid), None)
        out.append(Notice(
            NoticeKind.WAYPOINT_REACHED, voyage_id,
            title=f"Waypoint reached: {wp.title if wp else wid}",
            body="Every leg on it is done.",
            waypoint=wid))
    return out


# ------------------------------------------------------------------------- standing


def standing(
    loaded: LoadedVoyage,
    *,
    now: Clock = today,
    drift_days: int = 7,
    lead_days: int = 14,
) -> list[Notice]:
    """Time/state Notices for one Voyage: arrival, drift, and long-lead reminders.

    An ``arrived`` Voyage yields only its arrival Notice (it can't drift or nag). An
    ``active`` Voyage with no logbook entry in ``drift_days`` drifts. A leg with a
    ``needs`` list whose waypoint ``target`` is within ``lead_days`` (and not yet
    started) raises a long-lead order reminder.
    """
    v = loaded.voyage
    chart = loaded.chart          # already DAG-resolved by open_voyage/load_chart
    vid = v.id
    out: list[Notice] = []
    today_d = date.fromisoformat(now())

    if v.status is VoyageStatus.ARRIVED:
        return [Notice(NoticeKind.ARRIVAL, vid,
                       title=f"Arrived: {v.title}",
                       body="This Voyage reached port.")]

    if v.status is VoyageStatus.ACTIVE:
        dates = [e.date for e in logbook.load(loaded.vdir) if _valid_date(e.date)]
        if dates:
            gap = (today_d - date.fromisoformat(max(dates))).days
            if gap >= drift_days:
                out.append(Notice(
                    NoticeKind.DRIFT, vid,
                    title=f"{v.title} has been quiet",
                    body=f"No log entry in {gap} days — still on it?"))

    wp_target = {w.id: w.target for w in chart.waypoints if _valid_date(w.target)}
    for leg in _flat(chart).values():
        if not leg.needs or leg.waypoint not in wp_target:
            continue
        # Only remind while there's still ordering to do — not once it's under way.
        if leg.status in (LegStatus.DONE, LegStatus.DROPPED, LegStatus.ACTIVE):
            continue
        days_left = (date.fromisoformat(wp_target[leg.waypoint]) - today_d).days
        if 0 <= days_left <= lead_days:
            items = ", ".join(_need_label(n) for n in leg.needs)
            out.append(Notice(
                NoticeKind.LONG_LEAD, vid,
                title=f"Order soon for: {leg.title}",
                body=f"Needs {items} to hit its waypoint in {days_left} days.",
                leg=leg.id, waypoint=leg.waypoint))
    return out


__all__ = ["NoticeKind", "Notice", "transitions", "standing"]
