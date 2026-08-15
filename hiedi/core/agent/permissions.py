"""The permission broker — gates every tool call against the per-Voyage policy.

Policy comes from ``.hiedi/config.yaml`` (:class:`~hiedi.core.model.VoyageConfig`):

* ``allow`` — run silently.
* ``deny``  — never run; raise :class:`PermissionDenied`.
* ``ask``   — ask the human. The ask itself is an **injected callback**, so the core
  stays UI-free: the daemon supplies one that emits a D-Bus prompt and waits; a test
  supplies a canned answer. A ``session`` grant is remembered for the rest of the run so
  the human isn't re-asked for the same tool.

The default asker denies — fail closed. Nothing runs on ``ask`` unless someone wired a
real answer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from ..model import Permission, VoyageConfig


class Decision(str, Enum):
    DENY = "deny"
    ALLOW_ONCE = "allow_once"
    ALLOW_SESSION = "allow_session"   # remember for the rest of this run


@dataclass(frozen=True)
class ToolRequest:
    """What the human is being asked to approve."""

    tool: str
    summary: str                     # one-line, human-readable
    mutates: bool
    reversible: bool
    detail: str = ""                 # optional expanded context (e.g. a diff/preview)


@dataclass(frozen=True)
class Grant:
    tool: str
    allowed: bool
    decision: Decision
    asked: bool                      # did we prompt the human for this one?


class PermissionDenied(PermissionError):
    def __init__(self, tool: str) -> None:
        super().__init__(f"permission denied for tool '{tool}'")
        self.tool = tool


# asker(request) -> Decision
Asker = Callable[[ToolRequest], Decision]


def deny_all(_req: ToolRequest) -> Decision:
    """The safe default asker: refuse anything that needs asking."""
    return Decision.DENY


class PermissionBroker:
    def __init__(self, config: VoyageConfig, *, asker: Asker = deny_all) -> None:
        self._config = config
        self._asker = asker
        self._session_grants: set[str] = set()

    def policy(self, tool: str) -> Permission:
        return self._config.permission_for(tool)

    def check(self, request: ToolRequest) -> Grant:
        """Resolve a tool request to a :class:`Grant` (may prompt via the asker)."""
        policy = self.policy(request.tool)

        if policy is Permission.DENY:
            return Grant(request.tool, False, Decision.DENY, asked=False)

        if policy is Permission.ALLOW:
            return Grant(request.tool, True, Decision.ALLOW_ONCE, asked=False)

        # policy is ASK
        if request.tool in self._session_grants:
            return Grant(request.tool, True, Decision.ALLOW_SESSION, asked=False)

        decision = self._asker(request)
        if decision is Decision.ALLOW_SESSION:
            self._session_grants.add(request.tool)
        allowed = decision in (Decision.ALLOW_ONCE, Decision.ALLOW_SESSION)
        return Grant(request.tool, allowed, decision, asked=True)

    def require(self, request: ToolRequest) -> Grant:
        """Like :meth:`check` but raise :class:`PermissionDenied` when refused."""
        grant = self.check(request)
        if not grant.allowed:
            raise PermissionDenied(request.tool)
        return grant


__all__ = [
    "Decision", "ToolRequest", "Grant", "PermissionDenied",
    "Asker", "deny_all", "PermissionBroker",
]
