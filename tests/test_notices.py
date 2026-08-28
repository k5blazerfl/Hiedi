"""Plan-state Notices are computed from the pure model — no brain, no bus."""

from __future__ import annotations

from hiedi.core import notices, store
from hiedi.core.model import Chart, Leg, LegStatus, VoyageStatus, Waypoint
from hiedi.core.notices import NoticeKind


# -- transitions ---------------------------------------------------------------


def _chart(measure_done: bool = False) -> Chart:
    return Chart(
        waypoints=[Waypoint(id="w", title="Site")],
        legs=[
            Leg(id="measure", title="Measure pad", waypoint="w",
                status=LegStatus.DONE if measure_done else LegStatus.TODO),
            Leg(id="order", title="Order panels", waypoint="w", after=["measure"]),
        ],
    )


def test_leg_becomes_ready():
    got = notices.transitions(_chart(measure_done=False), _chart(measure_done=True), "v")
    kinds = {(n.kind, n.leg) for n in got}
    assert (NoticeKind.LEG_READY, "order") in kinds
    # 'measure' went done, not ready — no spurious leg_ready for it
    assert (NoticeKind.LEG_READY, "measure") not in kinds


def test_leg_becomes_blocked():
    # regressing 'measure' from done → todo re-blocks 'order'
    got = notices.transitions(_chart(measure_done=True), _chart(measure_done=False), "v")
    assert any(n.kind is NoticeKind.BLOCKER and n.leg == "order" for n in got)


def test_new_blocked_leg_is_not_news():
    before = Chart(waypoints=[Waypoint("w", "W")], legs=[])
    after = Chart(waypoints=[Waypoint("w", "W")],
                  legs=[Leg(id="x", title="X", waypoint="w", after=["missing"])])
    got = notices.transitions(before, after, "v")
    assert not any(n.kind is NoticeKind.BLOCKER for n in got)


def test_waypoint_reached():
    before = _chart(measure_done=True)      # 'order' still open
    after = Chart(waypoints=[Waypoint(id="w", title="Site")],
                  legs=[Leg(id="measure", title="m", waypoint="w", status=LegStatus.DONE),
                        Leg(id="order", title="o", waypoint="w", status=LegStatus.DONE)])
    got = notices.transitions(before, after, "v")
    assert any(n.kind is NoticeKind.WAYPOINT_REACHED and n.waypoint == "w" for n in got)


def test_notice_key_dedups_same_event():
    a = notices.transitions(_chart(False), _chart(True), "v")[0]
    b = notices.transitions(_chart(False), _chart(True), "v")[0]
    assert a.key() == b.key()


# -- standing (arrival / drift / long-lead) ------------------------------------


def _active_voyage(root, clock, *, chart: Chart | None = None,
                   status: VoyageStatus = VoyageStatus.ACTIVE):
    vdir = store.create_voyage("Backyard greenhouse", root=root, now=clock)
    v = store.load_voyage(vdir)
    v.status = status
    store.save_voyage(vdir, v)
    if chart is not None:
        store.save_chart(vdir, chart)
    return store.open_voyage(vdir.path)


def test_arrival_short_circuits(root, clock):
    loaded = _active_voyage(root, clock, status=VoyageStatus.ARRIVED)
    got = notices.standing(loaded, now=lambda: "2026-09-30")
    assert [n.kind for n in got] == [NoticeKind.ARRIVAL]      # no drift on an arrived Voyage


def test_drift_on_quiet_active_voyage(root, clock):
    # create_voyage stamps a logbook entry at the clock date (2026-08-15)
    loaded = _active_voyage(root, clock)
    quiet = notices.standing(loaded, now=lambda: "2026-08-18", drift_days=7)
    assert not any(n.kind is NoticeKind.DRIFT for n in quiet)   # 3 days — fine
    drifted = notices.standing(loaded, now=lambda: "2026-08-30", drift_days=7)
    assert any(n.kind is NoticeKind.DRIFT for n in drifted)     # 15 days — quiet


def test_long_lead_reminder(root, clock):
    chart = Chart(
        waypoints=[Waypoint(id="glaze", title="Glazing", target="2026-08-25")],
        legs=[Leg(id="order-poly", title="Order polycarbonate", waypoint="glaze",
                  needs=["twin-wall polycarbonate"])],
    )
    loaded = _active_voyage(root, clock, chart=chart)
    got = notices.standing(loaded, now=lambda: "2026-08-15", lead_days=14)   # 10 days out
    ll = [n for n in got if n.kind is NoticeKind.LONG_LEAD]
    assert ll and ll[0].leg == "order-poly"
    assert "polycarbonate" in ll[0].body
    # far outside the lead window → no reminder
    early = notices.standing(loaded, now=lambda: "2026-07-01", lead_days=14)
    assert not any(n.kind is NoticeKind.LONG_LEAD for n in early)
