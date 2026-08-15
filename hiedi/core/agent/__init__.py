"""The agent layer — the permission broker, the tool registry, and the engine loop.

This is the "act" end of the suggest→act dial. Every effect Hiedi has on your files
passes through the broker (deny/ask/allow, per-Voyage), is applied reversibly, and is
recorded with ``by:``/``model:`` attribution. The broker's *ask* is injected, so the
pure core never touches a bus or a UI — the daemon wires a real prompt, tests wire a
canned answer.
"""

from .permissions import (
    Decision,
    Grant,
    PermissionBroker,
    PermissionDenied,
    ToolRequest,
)
from .tools import TOOLS, Tool, ToolContext, ToolResult, get_tool
from .engine import AgentEngine, DraftResult, TurnResult

__all__ = [
    "Decision", "Grant", "PermissionBroker", "PermissionDenied", "ToolRequest",
    "TOOLS", "Tool", "ToolContext", "ToolResult", "get_tool",
    "AgentEngine", "DraftResult", "TurnResult",
]
