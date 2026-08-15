"""Shared fixtures — a fixed clock and an isolated Voyages root."""

from __future__ import annotations

import json

import pytest

from hiedi.core import store
from hiedi.core.brain.base import Reply


@pytest.fixture
def clock():
    return lambda: "2026-08-15"


@pytest.fixture
def root(tmp_path):
    return tmp_path / "Voyages"


@pytest.fixture
def voyage(root, clock):
    return store.create_voyage(
        "Backyard greenhouse", root=root,
        success=["Frame level", "Under budget"], now=clock)


CHART_JSON = json.dumps({
    "waypoints": [
        {"id": "site-ready", "title": "Site prepped", "target": "2026-08-30"},
        {"id": "shell-up", "title": "Frame standing"},
    ],
    "legs": [
        {"id": "measure", "title": "Measure pad", "waypoint": "site-ready", "after": []},
        {"id": "order", "title": "Order panels", "waypoint": "site-ready",
         "after": ["measure"], "notes": "long-lead"},
        {"id": "frame", "title": "Build frame", "waypoint": "shell-up", "after": ["order"]},
    ],
})


class FakeBrain:
    """A deterministic brain: returns a fixed Chart JSON, no network."""

    name = "local"
    model = "qwen3-coder:latest"

    def __init__(self, content: str = "```json\n" + CHART_JSON + "\n```") -> None:
        self._content = content

    def available(self) -> bool:
        return True

    def chat(self, messages, *, temperature=0.7) -> Reply:
        return Reply(content=self._content, brain=self.name, model=self.model)

    def stream(self, messages, *, temperature=0.7):
        yield self._content


@pytest.fixture
def fake_brain():
    return FakeBrain()
