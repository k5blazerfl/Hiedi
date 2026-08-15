"""The captain's log — an append-only, dated, attributed Markdown narrative.

This is where *why* lives (decisions, dead-ends, blockers) — the memory a checklist
can't hold. The format is deliberately plain so it stays hand-editable:

    ## 2026-08-15 · decision · by:charron
    Going twin-wall polycarbonate over glass — lighter, safer on the old pad. → [shell-up]

Entries are appended (newest at the bottom). A ``milestone`` entry is written
automatically when a Waypoint's legs all reach ``done`` — :func:`newly_completed_waypoints`
computes that transition so the caller (the agent engine) can log it once.
"""

from __future__ import annotations

import re

from .model import Chart, LegStatus, LogEntry, LOG_TYPES
from .store import Clock, VoyageDir, today

# "## <date> · <type> · by:<who>[ · model:<model>]"
_HEADER = re.compile(
    r"^##\s+(?P<date>\d{4}-\d{2}-\d{2})\s+·\s+(?P<type>\w+)\s+·\s+by:(?P<by>\S+)"
    r"(?:\s+·\s+model:(?P<model>\S+))?\s*$"
)
_LEG_LINK = re.compile(r"\[([a-z0-9][a-z0-9\-]*)\]")


def format_entry(entry: LogEntry) -> str:
    """Render one entry to its Markdown block (no trailing blank line)."""
    head = f"## {entry.date} · {entry.type} · by:{entry.by}"
    if entry.model:
        head += f" · model:{entry.model}"
    body = entry.body.rstrip()
    if entry.legs:
        links = " ".join(f"[{lid}]" for lid in entry.legs)
        body = f"{body} → {links}" if body else f"→ {links}"
    return f"{head}\n{body}\n"


def append(
    vdir: VoyageDir,
    body: str,
    *,
    type: str = "note",
    by: str = "user",
    model: str | None = None,
    legs: list[str] | None = None,
    now: Clock = today,
) -> LogEntry:
    """Append an entry to ``logbook.md`` and return it.

    Unknown ``type`` values are tolerated (kept verbatim) — the vocab in
    :data:`hiedi.core.model.LOG_TYPES` is guidance, not a hard schema.
    """
    entry = LogEntry(date=now(), type=type, by=by, model=model,
                     body=body, legs=list(legs or []))
    text = format_entry(entry)
    path = vdir.logbook_file
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    # Blank line between blocks for readability.
    sep = "\n" if existing else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(existing + sep + text, encoding="utf-8")
    import os
    os.replace(tmp, path)
    return entry


def parse(text: str) -> list[LogEntry]:
    """Parse a logbook body back into entries (best-effort; ignores prose headers)."""
    entries: list[LogEntry] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _HEADER.match(lines[i])
        if not m:
            i += 1
            continue
        i += 1
        body_lines: list[str] = []
        while i < len(lines) and not _HEADER.match(lines[i]):
            body_lines.append(lines[i])
            i += 1
        body = "\n".join(body_lines).strip()
        legs = _LEG_LINK.findall(body)
        entries.append(LogEntry(
            date=m["date"], type=m["type"], by=m["by"], model=m["model"],
            body=body, legs=legs,
        ))
    return entries


def load(vdir: VoyageDir) -> list[LogEntry]:
    path = vdir.logbook_file
    if not path.exists():
        return []
    return parse(path.read_text(encoding="utf-8"))


def _waypoint_done(chart: Chart, waypoint_id: str) -> bool:
    """True if the waypoint has ≥1 leg and every leg on it is done/dropped."""
    legs = [l for l in chart.legs if l.waypoint == waypoint_id]
    if not legs:
        return False
    return all(l.status in (LegStatus.DONE, LegStatus.DROPPED) for l in legs)


def completed_waypoints(chart: Chart) -> set[str]:
    """The set of waypoint ids whose legs are all done."""
    return {w.id for w in chart.waypoints if _waypoint_done(chart, w.id)}


def newly_completed_waypoints(before: Chart, after: Chart) -> list[str]:
    """Waypoint ids that became complete between ``before`` and ``after``.

    Lets the agent engine log a milestone exactly once, on the transition.
    """
    was = completed_waypoints(before)
    now_done = completed_waypoints(after)
    order = {w.id: i for i, w in enumerate(after.waypoints)}
    return sorted(now_done - was, key=lambda wid: order.get(wid, 1_000_000))


__all__ = [
    "format_entry", "append", "parse", "load",
    "completed_waypoints", "newly_completed_waypoints",
    "LOG_TYPES",
]
