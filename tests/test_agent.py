"""The broker gates every mutation and the engine attributes + logs its effects."""

from __future__ import annotations

import pytest

from hiedi.core import logbook, store
from hiedi.core.agent import AgentEngine
from hiedi.core.agent.permissions import (
    Decision,
    PermissionBroker,
    PermissionDenied,
    ToolRequest,
)
from hiedi.core.brain.router import Router
from hiedi.core.model import Permission, VoyageConfig

from conftest import FakeBrain


# -- broker --------------------------------------------------------------------


def _req(tool="write_chart"):
    return ToolRequest(tool, "summary", True, True)


def test_broker_allow_and_deny_need_no_ask():
    cfg = VoyageConfig()
    asked = []
    broker = PermissionBroker(cfg, asker=lambda r: asked.append(r) or Decision.ALLOW_ONCE)
    assert broker.check(_req("write_logbook")).allowed      # allow policy
    assert not broker.check(_req("run_command")).allowed     # deny policy
    assert asked == []                                       # neither prompted


def test_broker_ask_prompts_and_session_grant_sticks():
    cfg = VoyageConfig()
    calls = []
    broker = PermissionBroker(cfg, asker=lambda r: calls.append(r.tool) or Decision.ALLOW_SESSION)
    assert broker.check(_req("write_chart")).allowed
    assert broker.check(_req("write_chart")).allowed         # second time: no prompt
    assert calls == ["write_chart"]                          # asked exactly once


def test_broker_default_fails_closed():
    broker = PermissionBroker(VoyageConfig())  # default asker denies
    assert not broker.check(_req("write_chart")).allowed


def test_broker_require_raises():
    broker = PermissionBroker(VoyageConfig())
    with pytest.raises(PermissionDenied):
        broker.require(_req("web_fetch"))


# -- engine --------------------------------------------------------------------


def _engine(asker, clock):
    return AgentEngine(Router(FakeBrain()), asker=asker, now=clock)


def test_draft_chart_applies_attributes_and_logs(voyage, clock):
    loaded = store.open_voyage(voyage.path)
    res = _engine(lambda r: Decision.ALLOW_SESSION, clock).draft_chart(loaded)
    assert res.applied
    # legs attributed to hiedi + the model
    leg = loaded.chart.leg("measure")
    assert leg.by == "hiedi" and leg.model == "qwen3-coder:latest"
    # DAG resolved on write
    assert loaded.chart.leg("order").status.value == "blocked"
    # a progress entry was logged, attributed
    types = [e.type for e in logbook.load(loaded.vdir)]
    assert "progress" in types


def test_draft_denied_does_not_write(voyage, clock):
    loaded = store.open_voyage(voyage.path)
    loaded.config.permissions["write_chart"] = Permission.DENY
    res = _engine(lambda r: Decision.ALLOW_ONCE, clock).draft_chart(loaded)
    assert not res.applied
    assert store.load_chart(voyage).legs == []               # nothing written


def test_toggle_leg_completes_waypoint_and_logs_milestone(voyage, clock):
    loaded = store.open_voyage(voyage.path)
    eng = _engine(lambda r: Decision.ALLOW_SESSION, clock)
    eng.draft_chart(loaded)

    loaded = store.open_voyage(voyage.path)
    eng.toggle_leg(loaded, "measure", done=True)
    loaded = store.open_voyage(voyage.path)
    res = eng.toggle_leg(loaded, "order", done=True)         # completes site-ready
    assert "site-ready" in res.milestones
    milestone_bodies = [e.body for e in logbook.load(voyage) if e.type == "milestone"]
    assert any("Site prepped" in b for b in milestone_bodies)


def test_toggle_unknown_leg(voyage, clock):
    loaded = store.open_voyage(voyage.path)
    res = _engine(lambda r: Decision.ALLOW_ONCE, clock).toggle_leg(loaded, "ghost", done=True)
    assert not res.applied and "no such leg" in res.message
