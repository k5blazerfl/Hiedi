"""The durable, user-owned data model — Voyage / Chart / Logbook.

Promoted from ``voyage-data-model.md`` v0.1. Design commitments encoded here:

* **User owns the data, in plain text.** Structured parts are YAML, narrative is
  Markdown. Every dataclass has a ``to_dict``/``from_dict`` so the store is a thin
  IO layer over these.
* **Domain-neutral.** A Voyage is a build, a trip, a thesis, a release — nothing in the
  schema assumes code.
* **Faithful & attributed.** Fields Hiedi writes carry ``by`` and ``model``.
* **A plan is a DAG, not a checklist.** :class:`Leg` names its ``after`` deps; the store's
  resolver derives ``ready`` vs ``blocked`` (see :mod:`hiedi.core.store`).

Serialization is deliberately lossless-ish and tolerant: unknown keys are ignored on
load and omitted-when-empty on dump, so a hand-edited file round-trips cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

SCHEMA_VOYAGE = "hiedi.voyage/0.1"
SCHEMA_CHART = "hiedi.chart/0.1"
SCHEMA_CONFIG = "hiedi.config/0.1"


class VoyageStatus(str, Enum):
    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    ARRIVED = "arrived"
    ABANDONED = "abandoned"


class LegStatus(str, Enum):
    TODO = "todo"
    READY = "ready"      # all `after` deps done — usually derived, may be set explicitly
    ACTIVE = "active"
    BLOCKED = "blocked"
    DONE = "done"
    DROPPED = "dropped"


class Consent(str, Enum):
    """The per-Voyage cloud gate and the per-tool permission dial share this vocab."""

    NEVER = "never"
    ASK = "ask"
    ALLOW = "allow"


# `deny` is the permission-broker spelling of "never"; kept distinct so a tool config
# reads naturally (`run_command: deny`) while a cloud gate reads (`cloud: never`).
class Permission(str, Enum):
    DENY = "deny"
    ASK = "ask"
    ALLOW = "allow"


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is None or an empty list/dict, for tidy YAML."""
    return {k: v for k, v in d.items() if v not in (None, [], {})}


# --------------------------------------------------------------------------- Chart


@dataclass
class Estimate:
    effort: str | None = None   # freeform: "2h", "8-12h", "3 days"
    cost: float | None = None
    currency: str = "USD"

    def to_dict(self) -> dict[str, Any]:
        return _clean({"effort": self.effort, "cost": self.cost,
                       "currency": self.currency if self.cost is not None else None})

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Estimate | None":
        if not d:
            return None
        return cls(effort=d.get("effort"), cost=d.get("cost"),
                   currency=d.get("currency", "USD"))


@dataclass
class Leg:
    """A task. Legs form a DAG via ``after`` and may nest via ``sub``."""

    id: str
    title: str
    waypoint: str | None = None
    status: LegStatus = LegStatus.TODO
    crew: str | None = None
    estimate: Estimate | None = None
    after: list[str] = field(default_factory=list)
    needs: list[Any] = field(default_factory=list)      # freeform items or {item,qty,have}
    produces: list[str] = field(default_factory=list)
    sub: list["Leg"] = field(default_factory=list)
    notes: str | None = None
    by: str | None = None          # "user" | "hiedi"
    model: str | None = None       # which brain drafted it, when by == "hiedi"

    def to_dict(self) -> dict[str, Any]:
        return _clean({
            "id": self.id,
            "title": self.title,
            "waypoint": self.waypoint,
            "status": self.status.value,
            "crew": self.crew,
            "estimate": self.estimate.to_dict() if self.estimate else None,
            "after": list(self.after),
            "needs": list(self.needs),
            "produces": list(self.produces),
            "sub": [s.to_dict() for s in self.sub],
            "notes": self.notes,
            "by": self.by,
            "model": self.model,
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Leg":
        return cls(
            id=str(d["id"]),
            title=d.get("title", ""),
            waypoint=d.get("waypoint"),
            status=LegStatus(d.get("status", "todo")),
            crew=d.get("crew"),
            estimate=Estimate.from_dict(d.get("estimate")),
            after=list(d.get("after") or []),
            needs=list(d.get("needs") or []),
            produces=list(d.get("produces") or []),
            sub=[cls.from_dict(s) for s in (d.get("sub") or [])],
            notes=d.get("notes"),
            by=d.get("by"),
            model=d.get("model"),
        )


@dataclass
class Waypoint:
    """An ordered milestone — a 'port' on the route."""

    id: str
    title: str
    target: str | None = None      # ISO date string; kept as str to round-trip exactly

    def to_dict(self) -> dict[str, Any]:
        return _clean({"id": self.id, "title": self.title, "target": self.target})

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Waypoint":
        return cls(id=str(d["id"]), title=d.get("title", ""), target=d.get("target"))


@dataclass
class Chart:
    """The plan: ordered waypoints + a DAG of legs."""

    waypoints: list[Waypoint] = field(default_factory=list)
    legs: list[Leg] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_CHART,
            "waypoints": [w.to_dict() for w in self.waypoints],
            "legs": [l.to_dict() for l in self.legs],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Chart":
        d = d or {}
        return cls(
            waypoints=[Waypoint.from_dict(w) for w in (d.get("waypoints") or [])],
            legs=[Leg.from_dict(l) for l in (d.get("legs") or [])],
        )

    def leg(self, leg_id: str) -> Leg | None:
        """Find a leg by id, searching nested sub-legs too."""
        def walk(legs: list[Leg]) -> Leg | None:
            for leg in legs:
                if leg.id == leg_id:
                    return leg
                hit = walk(leg.sub)
                if hit:
                    return hit
            return None
        return walk(self.legs)


# --------------------------------------------------------------------------- Voyage


@dataclass
class Budget:
    amount: float | None = None
    currency: str = "USD"

    def to_dict(self) -> dict[str, Any]:
        return _clean({"amount": self.amount,
                       "currency": self.currency if self.amount is not None else None})

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Budget | None":
        if not d:
            return None
        return cls(amount=d.get("amount"), currency=d.get("currency", "USD"))


@dataclass
class Constraints:
    deadline: str | None = None
    budget: Budget | None = None
    other: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _clean({
            "deadline": self.deadline,
            "budget": self.budget.to_dict() if self.budget else None,
            "other": list(self.other),
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Constraints":
        d = d or {}
        return cls(deadline=d.get("deadline"), budget=Budget.from_dict(d.get("budget")),
                   other=list(d.get("other") or []))


@dataclass
class Voyage:
    """The manifest: where we're sailing and the rules of the voyage."""

    id: str
    title: str
    kind: str = "build"                  # freeform tag
    destination: str = ""                # the goal, in the user's words
    success: list[str] = field(default_factory=list)
    constraints: Constraints = field(default_factory=Constraints)
    status: VoyageStatus = VoyageStatus.PLANNING
    tags: list[str] = field(default_factory=list)
    crew: list[str] = field(default_factory=lambda: ["hiedi"])
    cloud: Consent = Consent.ASK         # consent policy governing Claude use
    created: str | None = None
    updated: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _clean({
            "schema": SCHEMA_VOYAGE,
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "destination": self.destination,
            "success": list(self.success),
            "constraints": self.constraints.to_dict(),
            "status": self.status.value,
            "tags": list(self.tags),
            "crew": list(self.crew),
            "cloud": self.cloud.value,
            "created": self.created,
            "updated": self.updated,
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Voyage":
        return cls(
            id=str(d["id"]),
            title=d.get("title", ""),
            kind=d.get("kind", "build"),
            destination=d.get("destination", ""),
            success=list(d.get("success") or []),
            constraints=Constraints.from_dict(d.get("constraints")),
            status=VoyageStatus(d.get("status", "planning")),
            tags=list(d.get("tags") or []),
            crew=list(d.get("crew") or ["hiedi"]),
            cloud=Consent(d.get("cloud", "ask")),
            created=d.get("created"),
            updated=d.get("updated"),
        )


# --------------------------------------------------------------- per-Voyage config


DEFAULT_PERMISSIONS: dict[str, Permission] = {
    "read_resources": Permission.ALLOW,
    "write_chart": Permission.ASK,
    "write_logbook": Permission.ALLOW,
    "run_command": Permission.DENY,
    "web_fetch": Permission.ASK,
}


@dataclass
class Routing:
    default: str = "local"                 # "local" (Ollama) unless escalated
    local_model: str = "qwen3-coder:latest"
    cloud_model: str = "claude-opus-4-8"
    escalate_when: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _clean({
            "default": self.default,
            "local_model": self.local_model,
            "cloud_model": self.cloud_model,
            "escalate_when": list(self.escalate_when),
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Routing":
        d = d or {}
        return cls(
            default=d.get("default", "local"),
            local_model=d.get("local_model", "qwen3-coder:latest"),
            cloud_model=d.get("cloud_model", "claude-opus-4-8"),
            escalate_when=list(d.get("escalate_when") or []),
        )


@dataclass
class VoyageConfig:
    """`.hiedi/config.yaml` — the faithful contract, per Voyage."""

    routing: Routing = field(default_factory=Routing)
    cloud: Consent = Consent.ASK           # mirrors voyage.yaml; the effective gate
    permissions: dict[str, Permission] = field(
        default_factory=lambda: dict(DEFAULT_PERMISSIONS))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_CONFIG,
            "routing": self.routing.to_dict(),
            "cloud": self.cloud.value,
            "permissions": {k: v.value for k, v in self.permissions.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "VoyageConfig":
        d = d or {}
        perms = dict(DEFAULT_PERMISSIONS)
        for k, v in (d.get("permissions") or {}).items():
            try:
                perms[k] = Permission(v)
            except ValueError:
                pass  # ignore unknown permission values rather than crash on a typo
        return cls(
            routing=Routing.from_dict(d.get("routing")),
            cloud=Consent(d.get("cloud", "ask")),
            permissions=perms,
        )

    def permission_for(self, tool: str) -> Permission:
        return self.permissions.get(tool, Permission.ASK)


# --------------------------------------------------------------------------- Logbook


LOG_TYPES = ("note", "decision", "progress", "blocker", "milestone")


@dataclass
class LogEntry:
    """One captain's-log entry: dated, attributed, typed, may link legs by id."""

    date: str                    # "YYYY-MM-DD"
    type: str = "note"
    by: str = "user"
    model: str | None = None
    body: str = ""
    legs: list[str] = field(default_factory=list)   # linked leg ids


def new_config() -> VoyageConfig:
    """A fresh per-Voyage config with the documented defaults."""
    return VoyageConfig()


__all__ = [
    "SCHEMA_VOYAGE", "SCHEMA_CHART", "SCHEMA_CONFIG",
    "VoyageStatus", "LegStatus", "Consent", "Permission",
    "Estimate", "Leg", "Waypoint", "Chart",
    "Budget", "Constraints", "Voyage",
    "Routing", "VoyageConfig", "DEFAULT_PERMISSIONS",
    "LogEntry", "LOG_TYPES", "new_config",
    "replace",
]
