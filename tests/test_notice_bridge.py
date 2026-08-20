"""The daemon's NoticeBridge emits transitions always and de-dups standing notices."""

from __future__ import annotations

from hiedi.core import store
from hiedi.core.model import Chart, Leg, LegStatus, VoyageStatus, Waypoint
from hiedi.daemon.notice_bridge import NoticeBridge


class Rec:
    """A capturing emit callback: records (kind, voyage, title, body, leg, waypoint)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def __call__(self, *args) -> None:
        self.calls.append(args)

    @property
    def kinds(self) -> list[str]:
        return [c[0] for c in self.calls]


def _chart(measure_done: bool = False) -> Chart:
    return Chart(
        waypoints=[Waypoint(id="w", title="Site")],
        legs=[
            Leg(id="measure", title="Measure", waypoint="w",
                status=LegStatus.DONE if measure_done else LegStatus.TODO),
            Leg(id="order", title="Order panels", waypoint="w", after=["measure"]),
        ],
    )


def _drifting_voyage(root, clock):
    vdir = store.create_voyage("Backyard greenhouse", root=root, now=clock)
    v = store.load_voyage(vdir)
    v.status = VoyageStatus.ACTIVE
    store.save_voyage(vdir, v)
    return store.open_voyage(vdir.path)


# -- transitions ---------------------------------------------------------------


def test_on_mutation_emits_transitions():
    rec = Rec()
    nb = NoticeBridge(rec)
    n = nb.on_mutation(_chart(False), _chart(True), "v")
    assert n >= 1
    assert ("leg_ready", "v", "Ready to start: Order panels", "Its prerequisites are done.",
            "order", "w") in rec.calls


def test_transitions_are_not_deduped():
    rec = Rec()
    nb = NoticeBridge(rec)
    nb.on_mutation(_chart(False), _chart(True), "v")
    nb.on_mutation(_chart(False), _chart(True), "v")   # same edge again → fires again
    assert rec.kinds.count("leg_ready") == 2


def test_leg_and_waypoint_blank_when_absent():
    rec = Rec()
    NoticeBridge(rec).on_mutation(
        _chart(True),
        Chart(waypoints=[Waypoint("w", "Site")],
              legs=[Leg("measure", "m", waypoint="w", status=LegStatus.DONE),
                    Leg("order", "o", waypoint="w", status=LegStatus.DONE)]),
        "v")
    wp = next(c for c in rec.calls if c[0] == "waypoint_reached")
    assert wp[4] == "" and wp[5] == "w"          # no leg, waypoint = w


# -- standing (de-dup + re-surface) --------------------------------------------


def test_on_open_dedups_standing(root, clock):
    loaded = _drifting_voyage(root, clock)
    rec = Rec()
    nb = NoticeBridge(rec, now=lambda: "2026-08-30")   # 15 days quiet → drift
    assert nb.on_open(loaded) == 1
    assert "drift" in rec.kinds
    assert nb.on_open(loaded) == 0                      # same event not re-surfaced


def test_mutation_forgets_standing_so_it_can_resurface(root, clock):
    loaded = _drifting_voyage(root, clock)
    rec = Rec()
    nb = NoticeBridge(rec, now=lambda: "2026-08-30")
    assert nb.on_open(loaded) == 1
    assert nb.on_open(loaded) == 0
    nb.on_mutation(_chart(True), _chart(True), loaded.voyage.id)   # act on the Voyage
    assert nb.on_open(loaded) == 1                     # standing may re-surface


def test_sweep_over_explicit_voyages(root, clock):
    _drifting_voyage(root, clock)
    rec = Rec()
    nb = NoticeBridge(rec, now=lambda: "2026-08-30")
    emitted = nb.sweep(store.list_voyages(root))
    assert emitted == 1 and rec.kinds == ["drift"]
