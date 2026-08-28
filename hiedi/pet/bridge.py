"""``hiedi-pet`` — bridge the ``org.hede.hiedi`` daemon to the desktop pet.

Subscribes to the daemon's session-bus signals and drives the pet through its control
channel: ``Status`` becomes a mood pose, ``Say`` becomes a speech bubble. This process
*is* Hiedi's face on the desktop — the embodiment that replaces the Qt companion. The
brain (``hiedid``) and the body (``xpet`` / ``helm-pet``) stay separate; this is the
thin wire between them, so either end can be swapped without touching the other.

Like :mod:`hiedi.daemon.service`, ``dbus_next`` is imported lazily so the pure mapping
helpers below import and unit-test with no bus.
"""

from __future__ import annotations

import asyncio
import errno
import os

from ..daemon import BUS_NAME, INTERFACE, OBJECT_PATH
from .channel import PetChannel, event_default_path

# The daemon's four statuses onto the poses the placeholder skin can show today.
# xpet has idle / happy / sleeping / walk / dragged — no "thinking" or "concern"
# pose yet, so those collapse to a calm idle until a Hiedi skin adds dedicated
# frames (then add the states to xpet.h and extend this table).
STATUS_MOOD = {
    "idle": "idle",
    "thinking": "idle",
    "success": "happy",
    "concern": "idle",
}

SPEECH_MAX = 160  # a speech bubble is a glance, not a paragraph


def status_to_mood(status: str) -> str:
    """Map a daemon Status value to a pet mood (unknown → calm idle)."""
    return STATUS_MOOD.get(status, "idle")


def clamp_speech(text: str, limit: int = SPEECH_MAX) -> str:
    """One line, bounded length — long replies get an ellipsis."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def parse_events(buf: bytes) -> tuple[list[str], bytes]:
    """Split a raw read from the event FIFO into complete event names + remainder.

    Pure and line-oriented (the pet writes one event per line), so it unit-tests
    without a FIFO. A trailing partial line is returned as the remainder to prepend
    to the next read.
    """
    events: list[str] = []
    *lines, tail = buf.split(b"\n")
    for line in lines:
        name = line.decode("utf-8", "replace").strip()
        if name:
            events.append(name)
    return events, tail


def _open_event_fifo(path) -> int:
    """Create (as the reader/owner) and open the event FIFO, non-blocking.

    O_RDWR keeps a writer end open so reads never see EOF when the pet momentarily
    closes its write end between pokes.
    """
    try:
        os.mkfifo(path, 0o600)
    except FileExistsError:
        pass
    return os.open(path, os.O_RDWR | os.O_NONBLOCK)


async def _serve(channel: PetChannel, *, retries: int = 60) -> None:
    from dbus_next import BusType
    from dbus_next.aio import MessageBus

    bus = await MessageBus(bus_type=BusType.SESSION).connect()

    introspection = None
    for _ in range(retries):
        try:
            introspection = await bus.introspect(BUS_NAME, OBJECT_PATH)
            break
        except Exception:  # daemon not up yet — wait for it
            await asyncio.sleep(1.0)
    if introspection is None:
        raise RuntimeError(f"{BUS_NAME} not on the session bus — is hiedid running?")

    obj = bus.get_proxy_object(BUS_NAME, OBJECT_PATH, introspection)
    iface = obj.get_interface(INTERFACE)

    iface.on_status(lambda state: channel.mood(status_to_mood(state)))
    if hasattr(iface, "on_say"):
        iface.on_say(lambda text: channel.say(clamp_speech(text)))

    # wire #2: the pet reports interactions on the event FIFO; a poke summons Hiedi
    loop = asyncio.get_running_loop()
    evt_path = event_default_path()
    evt_fd = _open_event_fifo(evt_path)
    remainder = b""

    def on_event_readable() -> None:
        nonlocal remainder
        try:
            data = os.read(evt_fd, 4096)
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                return
            raise
        if not data:
            return
        events, remainder = parse_events(remainder + data)
        for name in events:
            if name == "poke" and hasattr(iface, "call_poke"):
                loop.create_task(iface.call_poke())

    loop.add_reader(evt_fd, on_event_readable)

    # present desktop notifications through the pet (gated by Do Not Disturb)
    async def _notifications() -> None:
        from ..core import presence as presence_mod
        from .notifications import monitor_notifications
        try:
            await monitor_notifications(channel, dnd_getter=lambda: presence_mod.load().dnd)
        except Exception as e:  # a monitor failure must not take down the bridge
            print(f"hiedi-pet: notification monitor unavailable: {e}")
    loop.create_task(_notifications())

    channel.mood("idle")
    channel.say("Hiedi online.")
    print(f"hiedi-pet: bridging {BUS_NAME} → {channel.path}")
    print(f"hiedi-pet: listening for pokes on {evt_path}")
    await asyncio.get_event_loop().create_future()  # run forever


def run() -> int:
    channel = PetChannel()
    try:
        asyncio.run(_serve(channel))
    except KeyboardInterrupt:
        print("\nhiedi-pet: stopping")
    except ImportError as e:
        print(f"hiedi-pet needs the daemon extra: pip install 'hiedi[daemon]' ({e})")
        return 1
    except RuntimeError as e:
        print(f"hiedi-pet: {e}")
        return 1
    return 0


__all__ = ["STATUS_MOOD", "status_to_mood", "clamp_speech", "parse_events", "run"]
