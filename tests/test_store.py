"""The store writes the right layout, resolves the DAG, and never clobbers."""

from __future__ import annotations

import pytest

from hiedi.core import store
from hiedi.core.model import Chart, Leg, LegStatus, Waypoint


def test_create_writes_skeleton(voyage):
    for name in ("voyage.yaml", "chart.yaml", "logbook.md"):
        assert (voyage.path / name).exists()
    assert voyage.config_file.exists()
    assert voyage.resources_dir.is_dir()


def test_create_refuses_to_clobber(root, clock):
    store.create_voyage("Dup", root=root, now=clock)
    with pytest.raises(FileExistsError):
        store.create_voyage("Dup", root=root, now=clock)


def test_slugify():
    assert store.slugify("Build a Backyard Greenhouse!") == "build-a-backyard-greenhouse"
    assert store.slugify("   ") == "voyage"


def _chart():
    return Chart(
        waypoints=[Waypoint(id="w", title="W")],
        legs=[
            Leg(id="measure", title="m", waypoint="w", status=LegStatus.DONE),
            Leg(id="order", title="o", waypoint="w", after=["measure"]),
            Leg(id="frame", title="f", waypoint="w", after=["order"]),
            Leg(id="free", title="free", waypoint="w"),
        ],
    )


def test_resolve_ready_blocked_and_free():
    derived = store.resolve(_chart())
    assert derived["order"] is LegStatus.READY     # dep done
    assert derived["frame"] is LegStatus.BLOCKED   # dep (order) not done
    assert derived["free"] is LegStatus.READY      # no deps
    assert derived["measure"] is LegStatus.DONE    # terminal preserved


def test_resolve_unknown_dep_stays_blocked():
    c = Chart(legs=[Leg(id="x", title="x", after=["ghost"])])
    assert store.resolve(c)["x"] is LegStatus.BLOCKED


def test_load_chart_is_resolved(voyage):
    store.save_chart(voyage, _chart())
    loaded = store.load_chart(voyage)
    assert loaded.leg("order").status is LegStatus.READY
    assert loaded.leg("frame").status is LegStatus.BLOCKED


def test_atomic_write_leaves_no_tmp(voyage):
    store.save_chart(voyage, _chart())
    assert not list(voyage.path.glob(".*.tmp"))


def test_list_and_find(root, clock):
    store.create_voyage("Alpha", root=root, now=clock)
    store.create_voyage("Beta", root=root, now=clock)
    slugs = {d.path.name for d in store.list_voyages(root)}
    assert slugs == {"alpha", "beta"}
    assert store.find_voyage("Alpha", root=root).voyage.title == "Alpha"
