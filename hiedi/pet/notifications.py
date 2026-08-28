"""Present desktop notifications through the pet.

Hiedi becomes a notifications *presenter*: she watches the session bus for
``org.freedesktop.Notifications.Notify`` calls — as a passive **monitor**, so she
does not own the service and the desktop's own notifications keep working — and
echoes the summary/body through the pet's speech bubble. Gated by Do Not Disturb
(the presence policy) and a short cooldown, so a burst of notifications never
turns into a chattering pet.

``dbus_next`` is imported lazily; :func:`format_notification` is pure and testable.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from .channel import PetChannel

NOTIFY_IFACE = "org.freedesktop.Notifications"


def format_notification(app: str, summary: str, body: str, *, limit: int = 220) -> str:
    """One tidy line from a Notify call's (app_name, summary, body)."""
    app = " ".join((app or "").split())
    summary = " ".join((summary or "").split())
    body = " ".join((body or "").split())
    line = summary
    if body and body != summary:
        line = f"{summary} — {body}" if summary else body
    if app and app.lower() not in line.lower():
        line = f"{app}: {line}"
    if len(line) > limit:
        line = line[: limit - 1].rstrip() + "…"
    return line


async def monitor_notifications(channel: PetChannel, *,
                                dnd_getter: Callable[[], bool] | None = None,
                                cooldown: float = 6.0) -> None:
    """Monitor Notify calls and speak them through ``channel`` (runs forever)."""
    from dbus_next import BusType, Message, MessageType
    from dbus_next.aio import MessageBus

    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    # Become a passive monitor (empty match-rule list = capture all; we filter to
    # Notify in the handler — a specific interface/member rule proved unreliable).
    # After BecomeMonitor the connection is monitor-only, so it disturbs nothing.
    await bus.call(Message(
        destination="org.freedesktop.DBus",
        path="/org/freedesktop/DBus",
        interface="org.freedesktop.DBus.Monitoring",
        member="BecomeMonitor",
        signature="asu",
        body=[[], 0],
    ))

    last = 0.0

    def on_message(msg) -> None:
        nonlocal last
        if msg.message_type != MessageType.METHOD_CALL:
            return
        if msg.interface != NOTIFY_IFACE or msg.member != "Notify":
            return
        # Notify(app_name s, replaces_id u, app_icon s, summary s, body s, ...)
        b = msg.body or []
        app = b[0] if len(b) > 0 else ""
        summary = b[3] if len(b) > 3 else ""
        body = b[4] if len(b) > 4 else ""
        if dnd_getter and dnd_getter():
            return
        now = time.monotonic()
        if now - last < cooldown:
            return
        line = format_notification(str(app), str(summary), str(body))
        if line:
            last = now
            channel.notify(line)   # standalone card + run-in choreography

    bus.add_message_handler(on_message)
    print("hiedi-pet: presenting desktop notifications")
    await asyncio.get_event_loop().create_future()  # run forever


__all__ = ["format_notification", "monitor_notifications"]
