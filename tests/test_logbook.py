"""The logbook appends, parses, and detects milestone transitions."""

from __future__ import annotations

from hiedi.core import logbook
from hiedi.core.model import Chart, Leg, LegStatus, Waypoint


def test_append_and_parse_round_trip(voyage, clock):
    logbook.append(voyage, "A decision.", type="decision", by="charron",
                   legs=["shell-up"], now=clock)
    logbook.append(voyage, "Hiedi progress.", type="progress", by="hiedi",
                   model="qwen3-coder", now=clock)
    entries = logbook.load(voyage)
    # entry 0 is the auto "Voyage created" milestone from create_voyage
    assert entries[-2].type == "decision" and entries[-2].by == "charron"
    assert entries[-2].legs == ["shell-up"]
    assert entries[-1].model == "qwen3-coder"


def test_format_includes_attribution_and_links():
    from hiedi.core.model import LogEntry
    text = logbook.format_entry(LogEntry(
        date="2026-08-15", type="progress", by="hiedi", model="qwen3-coder",
        body="did a thing", legs=["a", "b"]))
    assert "by:hiedi" in text and "model:qwen3-coder" in text
    assert "[a] [b]" in text


def _chart(order_done: bool):
    return Chart(
        waypoints=[Waypoint(id="site", title="Site"), Waypoint(id="shell", title="Shell")],
        legs=[
            Leg(id="measure", title="m", waypoint="site", status=LegStatus.DONE),
            Leg(id="order", title="o", waypoint="site",
                status=LegStatus.DONE if order_done else LegStatus.READY),
            Leg(id="frame", title="f", waypoint="shell", status=LegStatus.READY),
        ],
    )


def test_newly_completed_waypoints():
    before, after = _chart(False), _chart(True)
    assert logbook.newly_completed_waypoints(before, after) == ["site"]
    # no change once already complete
    assert logbook.newly_completed_waypoints(after, after) == []


def test_empty_waypoint_is_not_complete():
    c = Chart(waypoints=[Waypoint(id="empty", title="E")], legs=[])
    assert logbook.completed_waypoints(c) == set()
