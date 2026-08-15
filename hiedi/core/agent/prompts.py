"""Prompt construction and reply parsing for the planning agent.

The persona lives in ``hiedi/data/persona.md`` (editable, greppable). Chart drafting
asks the model for a strict JSON object so parsing is robust across local models;
:func:`parse_chart` is tolerant of code fences and surrounding prose.
"""

from __future__ import annotations

import json
import re
from importlib import resources

from ..brain.base import Message
from ..model import Chart, Leg, Voyage, Waypoint

_PERSONA_FALLBACK = "You are Hiedi, a faithful harbor-pilot planning assistant."


def persona() -> str:
    try:
        return resources.files("hiedi.data").joinpath("persona.md").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        return _PERSONA_FALLBACK


_CHART_INSTRUCTION = """\
Draft an initial plan (a "Chart") for this Voyage.

Return ONLY a JSON object, no prose, in exactly this shape:
{
  "waypoints": [
    {"id": "kebab-id", "title": "Milestone title", "target": "YYYY-MM-DD or null"}
  ],
  "legs": [
    {"id": "kebab-id", "title": "Task title", "waypoint": "waypoint-id",
     "after": ["other-leg-id"], "needs": ["material or info"],
     "produces": ["output"], "notes": "one short line, optional"}
  ]
}

Rules:
- 2-5 waypoints, ordered from first to last.
- 4-12 legs total. Use `after` to encode real dependencies (a DAG, not a flat list).
- ids are short kebab-case and unique. Every leg names an existing waypoint.
- Flag long-lead items in `notes`. Keep it lean and editable, not exhaustive.
- Do NOT set status; the app derives ready/blocked from `after`.
"""


def draft_chart_messages(voyage: Voyage) -> list[Message]:
    """System + user messages asking the brain to draft a Chart for ``voyage``."""
    lines = [f"Destination: {voyage.destination or voyage.title}"]
    if voyage.success:
        lines.append("Success looks like:")
        lines += [f"  - {s}" for s in voyage.success]
    c = voyage.constraints
    if c.deadline:
        lines.append(f"Deadline: {c.deadline}")
    if c.budget and c.budget.amount is not None:
        lines.append(f"Budget: {c.budget.amount} {c.budget.currency}")
    for o in c.other:
        lines.append(f"Constraint: {o}")
    lines.append("")
    lines.append(_CHART_INSTRUCTION)
    return [
        Message("system", persona()),
        Message("user", "\n".join(lines)),
    ]


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of a model reply, tolerating fences and stray prose."""
    m = _FENCE.search(text)
    candidate = m.group(1) if m else text
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    m = _OBJECT.search(candidate)
    if m:
        return json.loads(m.group(0))
    raise ValueError("no JSON object found in the model reply")


def parse_chart(text: str, *, by: str = "hiedi", model: str | None = None) -> Chart:
    """Parse a drafted Chart from a model reply, stamping attribution on each leg."""
    data = _extract_json(text)
    waypoints = [Waypoint.from_dict(w) for w in (data.get("waypoints") or [])]
    legs: list[Leg] = []
    for d in data.get("legs") or []:
        leg = Leg.from_dict({**d, "status": "todo"})  # status is derived, force open
        leg.by = by
        leg.model = model
        legs.append(leg)
    return Chart(waypoints=waypoints, legs=legs)


__all__ = ["persona", "draft_chart_messages", "parse_chart"]
