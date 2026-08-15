"""Chart parsing is robust to fences and prose; attribution is stamped."""

from __future__ import annotations

import pytest

from hiedi.core.agent import prompts
from hiedi.core.model import Voyage


def test_parse_fenced_json():
    text = 'Here you go:\n```json\n{"waypoints": [], "legs": [{"id":"a","title":"A"}]}\n```'
    chart = prompts.parse_chart(text, by="hiedi", model="qwen3-coder")
    assert chart.legs[0].id == "a"
    assert chart.legs[0].by == "hiedi" and chart.legs[0].model == "qwen3-coder"


def test_parse_bare_object_with_surrounding_prose():
    text = 'Sure! {"waypoints": [{"id":"w","title":"W"}], "legs": []} — hope that helps'
    chart = prompts.parse_chart(text)
    assert chart.waypoints[0].id == "w"


def test_parse_forces_open_status():
    chart = prompts.parse_chart('{"legs":[{"id":"a","title":"A","status":"done"}]}')
    # status is derived, never trusted from the model
    assert chart.legs[0].status.value == "todo"


def test_parse_no_json_raises():
    with pytest.raises(ValueError):
        prompts.parse_chart("no json here at all")


def test_draft_messages_include_persona_and_goal():
    v = Voyage(id="g", title="Greenhouse", destination="A greenhouse", success=["level"])
    msgs = prompts.draft_chart_messages(v)
    assert msgs[0].role == "system" and "Hiedi" in msgs[0].content
    assert "A greenhouse" in msgs[1].content and "level" in msgs[1].content
