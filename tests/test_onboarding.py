"""First-login seeding copies the packaged tour and never clobbers a returning user."""

from __future__ import annotations

from hiedi.core import logbook, onboarding, store
from hiedi.core.model import VoyageStatus


def test_seed_creates_the_tour(root, clock):
    vdir = onboarding.seed_onboarding(root=root, now=clock)
    assert vdir is not None and vdir.exists()

    loaded = store.open_voyage(vdir.path)
    assert loaded.voyage.id == "get-started"
    assert loaded.voyage.status is VoyageStatus.ACTIVE      # the tour starts under way
    assert loaded.voyage.cloud.value == "never"            # 100% local
    assert loaded.config.cloud.value == "never"
    assert len(loaded.chart.legs) == 16 and len(loaded.chart.waypoints) == 6

    entries = logbook.load(vdir)
    assert entries and entries[-1].date == "2026-08-15"    # stamped by the clock
    assert entries[-1].by == "hiedi"


def test_seed_is_idempotent(root, clock):
    onboarding.seed_onboarding(root=root, now=clock)
    assert onboarding.is_seeded(root=root)
    # a returning user is not re-seeded
    assert onboarding.seed_onboarding(root=root, now=clock) is None


def test_seed_preserves_user_edits(root, clock):
    vdir = onboarding.seed_onboarding(root=root, now=clock)
    vdir.chart_file.write_text("schema: hiedi.chart/0.1\nwaypoints: []\nlegs: []\n",
                               encoding="utf-8")
    onboarding.seed_onboarding(root=root, now=clock)       # no-op, keeps the edit
    assert store.open_voyage(vdir.path).chart.legs == []


def test_force_reseeds_from_template(root, clock):
    vdir = onboarding.seed_onboarding(root=root, now=clock)
    vdir.chart_file.write_text("schema: hiedi.chart/0.1\nwaypoints: []\nlegs: []\n",
                               encoding="utf-8")
    onboarding.seed_onboarding(root=root, now=clock, force=True)
    assert len(store.open_voyage(vdir.path).chart.legs) == 16
