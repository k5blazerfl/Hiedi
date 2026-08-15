"""``hiedid`` — Hiedi's per-user session daemon.

Owns the brain router + agent engine + active-Voyage state and exposes them on the
session bus as ``org.hede.hiedi`` (following the vault+daemon shape HeDE's Keychain
uses). The UI is a thin client: it calls methods, listens for streamed tokens and
status changes, and answers permission prompts. Keeping the engine here means heavy
model work and tool brokering live outside the GUI process.

``dbus_next`` is imported lazily (inside :mod:`hiedi.daemon.service`) so the rest of the
package — and the whole pure core — installs and tests without a bus binding present.
"""

BUS_NAME = "org.hede.hiedi"
OBJECT_PATH = "/org/hede/hiedi"
INTERFACE = "org.hede.hiedi.Assistant"

__all__ = ["BUS_NAME", "OBJECT_PATH", "INTERFACE"]
