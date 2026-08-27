"""The pet bridge: status→mood mapping, speech clamping, and the FIFO wire."""

from __future__ import annotations

import os
import threading

from hiedi.pet.bridge import STATUS_MOOD, clamp_speech, parse_events, status_to_mood
from hiedi.pet.channel import PetChannel, default_path, event_default_path


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
    assert event_default_path() == tmp_path / "hiedi-pet.evt"


# -- events (body → brain, pure parse) -----------------------------------------

def test_parse_events_splits_lines():
    events, rem = parse_events(b"poke\ngrab\n")
    assert events == ["poke", "grab"]
    assert rem == b""


def test_parse_events_keeps_partial_line():
    events, rem = parse_events(b"poke\npo")
    assert events == ["poke"]
    assert rem == b"po"                       # completed by the next read


def test_parse_events_ignores_blank_lines():
    events, _ = parse_events(b"\n\npoke\n\n")
    assert events == ["poke"]


def test_parse_events_the_bytes_xpet_writes():
    # exactly what xpet's emit_event() puts on the wire for a right-click
    events, rem = parse_events(b"poke\n")
    assert events == ["poke"] and rem == b""


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


def test_event_fifo_roundtrip(tmp_path):
    """The bridge owns/creates the event FIFO; the pet's `poke\\n` reads back."""
    from hiedi.pet.bridge import _open_event_fifo, parse_events

    path = tmp_path / "pet.evt"
    rfd = _open_event_fifo(path)          # bridge side: create + open reader
    try:
        assert path.is_fifo()
        wfd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)  # xpet side
        try:
            os.write(wfd, b"poke\n")
        finally:
            os.close(wfd)
        events, rem = parse_events(os.read(rfd, 4096))
        assert events == ["poke"] and rem == b""
    finally:
        os.close(rfd)


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
