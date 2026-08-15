"""The daemon's async↔sync prompt bridge resolves and fails closed."""

from __future__ import annotations

import threading
import time

from hiedi.core.agent.permissions import Decision, ToolRequest
from hiedi.daemon.bridge import PromptBridge


def _req():
    return ToolRequest("write_chart", "Update the Chart", True, True)


def test_respond_unblocks_asker():
    asks = []
    bridge = PromptBridge(lambda rid, req: asks.append((rid, req.tool)), timeout=5)
    out = {}

    def worker():
        out["d"] = bridge.asker(_req())

    t = threading.Thread(target=worker)
    t.start()
    # wait for the pending prompt to register
    for _ in range(50):
        if bridge.pending_ids():
            break
        time.sleep(0.01)
    rid = bridge.pending_ids()[0]
    assert bridge.respond(rid, Decision.ALLOW_SESSION) is True
    t.join(2)
    assert out["d"] is Decision.ALLOW_SESSION
    assert asks and asks[0][1] == "write_chart"


def test_timeout_fails_closed():
    bridge = PromptBridge(lambda rid, req: None, timeout=0.1)
    assert bridge.asker(_req()) is Decision.DENY


def test_undeliverable_prompt_denies():
    def boom(rid, req):
        raise RuntimeError("no UI attached")
    bridge = PromptBridge(boom, timeout=1)
    assert bridge.asker(_req()) is Decision.DENY


def test_respond_unknown_id():
    bridge = PromptBridge(lambda rid, req: None)
    assert bridge.respond("999", Decision.ALLOW_ONCE) is False
