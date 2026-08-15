"""The model round-trips losslessly and tolerates hand-edits."""

from __future__ import annotations

from hiedi.core.model import (
    Chart,
    Consent,
    Leg,
    LegStatus,
    Permission,
    Voyage,
    VoyageConfig,
    Waypoint,
    DEFAULT_PERMISSIONS,
)


def test_voyage_round_trip():
    v = Voyage(id="g", title="Greenhouse", destination="A greenhouse",
               success=["level"], tags=["garden"], cloud=Consent.NEVER)
    assert Voyage.from_dict(v.to_dict()) == v


def test_chart_round_trip_with_nesting():
    chart = Chart(
        waypoints=[Waypoint(id="w1", title="One", target="2026-09-01")],
        legs=[Leg(id="a", title="A", waypoint="w1",
                  sub=[Leg(id="a1", title="A1", status=LegStatus.DONE)])],
    )
    back = Chart.from_dict(chart.to_dict())
    assert back == chart
    assert back.leg("a1").status is LegStatus.DONE  # nested lookup


def test_from_dict_ignores_unknown_keys():
    leg = Leg.from_dict({"id": "x", "title": "X", "surprise": 1, "status": "ready"})
    assert leg.id == "x" and leg.status is LegStatus.READY


def test_config_defaults_and_bad_values():
    cfg = VoyageConfig.from_dict({"permissions": {"write_chart": "bogus",
                                                  "run_command": "allow"}})
    # bogus value ignored -> keeps default; valid override applied
    assert cfg.permission_for("write_chart") is DEFAULT_PERMISSIONS["write_chart"]
    assert cfg.permission_for("run_command") is Permission.ALLOW


def test_config_default_permissions_match_spec():
    cfg = VoyageConfig()
    assert cfg.permission_for("run_command") is Permission.DENY
    assert cfg.permission_for("write_chart") is Permission.ASK
    assert cfg.permission_for("write_logbook") is Permission.ALLOW
