"""The pet bridge: status→mood mapping, speech clamping, and the FIFO wire."""

from __future__ import annotations

import os
import threading

from hiedi.pet.bridge import STATUS_MOOD, clamp_speech, status_to_mood
from hiedi.pet.channel import PetChannel, default_path


# -- mapping (pure) ------------------------------------------------------------

def test_status_maps_to_mood():
    assert status_to_mood("idle") == "idle"
    assert status_to_mood("success") == "happy"
    # xpet has no thinking/concern pose yet → calm idle, not a crash
    assert status_to_mood("thinking") == "idle"
    assert status_to_mood("concern") == "idle"


def test_unknown_status_is_idle():
    assert status_to_mood("explode") == "idle"


def test_every_daemon_status_is_mapped():
    for s in ("idle", "thinking", "success", "concern"):
        assert s in STATUS_MOOD


def test_clamp_speech_collapses_whitespace():
    assert clamp_speech("  hello\n  there ") == "hello there"


def test_clamp_speech_truncates_long_text():
    out = clamp_speech("x" * 500, limit=10)
    assert len(out) == 10 and out.endswith("…")


# -- channel (graceful when no pet) --------------------------------------------

def test_say_when_no_pet_is_graceful(tmp_path):
    ch = PetChannel(tmp_path / "nope.ctl")          # FIFO never created
    assert ch.say("hi") is False                     # no raise
    assert ch.mood("happy") is False


def test_empty_say_is_dropped(tmp_path):
    assert PetChannel(tmp_path / "x.ctl").say("   ") is False


def test_default_path_honors_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert default_path() == tmp_path / "hiedi-pet.ctl"


# -- channel (real FIFO round-trip — the exact bytes xpet parses) --------------

def test_channel_writes_protocol_lines(tmp_path):
    fifo = tmp_path / "pet.ctl"
    os.mkfifo(fifo)
    # hold a reader open (O_RDWR) so the writer's O_WRONLY|NONBLOCK open succeeds
    reader = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
    try:
        ch = PetChannel(fifo)
        assert ch.say("Woof — Hiedi online.") is True
        assert ch.mood("happy") is True
        got = b""
        # drain what's available
        for _ in range(100):
            try:
                chunk = os.read(reader, 4096)
            except BlockingIOError:
                chunk = b""
            if not chunk:
                break
            got += chunk
        assert got == "say Woof — Hiedi online.\nmood happy\n".encode("utf-8")
    finally:
        os.close(reader)


def test_channel_write_does_not_block(tmp_path):
    """A reader that never reads must not hang the writer (NONBLOCK)."""
    fifo = tmp_path / "pet.ctl"
    os.mkfifo(fifo)
    reader = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
    try:
        ch = PetChannel(fifo)
        done = threading.Event()
        threading.Thread(target=lambda: (ch.say("hi"), done.set())).start()
        assert done.wait(timeout=2.0), "PetChannel.say blocked"
    finally:
        os.close(reader)
