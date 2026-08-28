"""Presence configuration — how present Hiedi is on the desktop.

A user-level *desktop* preference (global, **not** per-Voyage), stored at
``$XDG_CONFIG_HOME/hiedi/presence.yaml``. Pure and bus-free: the companion reads
it to pick a render mode and to gate proactive Notices. The interruption *budget*
(the hourly cap's accounting) is runtime state in the companion, not stored here;
this module only holds the standing policy. See ``docs/desktop-assistant.md`` §3/§6.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any

import yaml

SCHEMA_PRESENCE = "hiedi.presence/0.1"


class PresenceLevel(IntEnum):
    """The presence dial. Ordered, so ``>=`` reads naturally."""

    ON_WATCH = 0       # default — a quiet, first-class bar applet
    ON_DECK = 1        # an ambient layer-shell floater
    AT_YOUR_SIDE = 2   # + proactive speech bubbles
    FIRST_MATE = 3     # + idle animation, personality, sound

    @property
    def proactive(self) -> bool:
        """True for tiers that may surface a Notice unprompted (as a bubble)."""
        return self >= PresenceLevel.AT_YOUR_SIDE

    @property
    def floats(self) -> bool:
        """True for tiers that draw a floating character (not just the bar pin)."""
        return self >= PresenceLevel.ON_DECK

    @classmethod
    def coerce(cls, value: Any) -> "PresenceLevel":
        """Tolerant parse: accept an int, a name, or the enum; fall back to default."""
        if isinstance(value, cls):
            return value
        if isinstance(value, bool):  # avoid bool-is-int surprises
            return cls.ON_WATCH
        if isinstance(value, int):
            return cls(value) if value in cls._value2member_map_ else cls.ON_WATCH
        if isinstance(value, str):
            key = value.strip().upper().replace("-", "_").replace(" ", "_")
            return cls.__members__.get(key, cls.ON_WATCH)
        return cls.ON_WATCH


def config_path() -> Path:
    """``$XDG_CONFIG_HOME/hiedi/presence.yaml`` (honored at call time, for tests)."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "hiedi" / "presence.yaml"


@dataclass
class Presence:
    """The standing presence policy."""

    level: PresenceLevel = PresenceLevel.ON_WATCH
    dnd: bool = False                # Do Not Disturb — mutes all proactive surfacing
    hourly_cap: int = 3             # max proactive bubbles/hour (enforced at runtime)
    muted_kinds: list[str] = field(default_factory=list)   # NoticeKind values

    def muted(self, kind: Any) -> bool:
        """True if this Notice kind is individually silenced (accepts enum or str)."""
        k = getattr(kind, "value", kind)
        return k in self.muted_kinds

    def may_surface(self, kind: Any) -> bool:
        """Standing-policy verdict for surfacing ``kind`` proactively (a bubble).

        This is the config-level gate only — level is proactive, DND is off, and the
        kind isn't muted. The hourly cap and focus/fullscreen guard are runtime
        concerns layered on top by the companion.
        """
        return self.level.proactive and not self.dnd and not self.muted(kind)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_PRESENCE,
            "level": int(self.level),
            "dnd": self.dnd,
            "hourly_cap": self.hourly_cap,
            "muted_kinds": list(self.muted_kinds),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Presence":
        d = d or {}
        cap = d.get("hourly_cap", 3)
        return cls(
            level=PresenceLevel.coerce(d.get("level", PresenceLevel.ON_WATCH)),
            dnd=bool(d.get("dnd", False)),
            hourly_cap=int(cap) if isinstance(cap, (int, float)) and cap >= 0 else 3,
            muted_kinds=[str(k) for k in (d.get("muted_kinds") or [])],
        )


def load(path: Path | None = None) -> Presence:
    """Load the policy, returning defaults when the file is absent or malformed."""
    p = path or config_path()
    if not p.exists():
        return Presence()
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return Presence()
    return Presence.from_dict(data if isinstance(data, dict) else {})


def save(presence: Presence, path: Path | None = None) -> None:
    """Write the policy atomically (temp + replace, matching the store's discipline)."""
    p = path or config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(presence.to_dict(), sort_keys=False, allow_unicode=True)
    tmp = p.with_name(f".{p.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


__all__ = ["SCHEMA_PRESENCE", "PresenceLevel", "Presence", "config_path", "load", "save"]
