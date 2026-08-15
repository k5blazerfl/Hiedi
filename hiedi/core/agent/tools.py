"""The tool registry — Hiedi's "hands".

Each :class:`Tool` declares whether it mutates the Voyage, produces a human-readable
one-line summary for the permission prompt, applies its effect through the store (never
ad-hoc IO), and — where it can — returns an ``undo`` so an action is reversible. That
reversibility is a design commitment, not a nicety.

The five MVP tools mirror the data-model's ``permissions:`` block:

===============  =======  ==========  ============================================
tool             mutates  reversible  default policy
===============  =======  ==========  ============================================
read_resources   no       n/a         allow
write_chart      yes      yes         ask   (snapshots the prior chart)
write_logbook    yes      no*         allow (*append-only; undo would rewrite history)
run_command      yes      no          deny
web_fetch        no       n/a         ask
===============  =======  ==========  ============================================
"""

from __future__ import annotations

import subprocess
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .. import logbook, store
from ..model import Chart
from ..store import Clock, LoadedVoyage, today


@dataclass
class ToolContext:
    """What a tool operates on. Held by the engine, passed to each tool call."""

    loaded: LoadedVoyage
    by: str = "hiedi"
    model: str | None = None
    now: Clock = today


@dataclass
class ToolResult:
    ok: bool
    summary: str
    undo: Callable[[], None] | None = None   # None => not reversible
    data: Any = None


@dataclass(frozen=True)
class Tool:
    name: str
    mutates: bool
    reversible: bool
    summarize: Callable[[dict], str]          # args -> one-line prompt summary
    run: Callable[[ToolContext, dict], ToolResult]


# --------------------------------------------------------------------------- tools


def _sum_read_resources(args: dict) -> str:
    return "Read the Voyage's resources/ directory"


def _run_read_resources(ctx: ToolContext, args: dict) -> ToolResult:
    rdir = ctx.loaded.vdir.resources_dir
    names = sorted(p.name for p in rdir.iterdir()) if rdir.is_dir() else []
    return ToolResult(True, f"read {len(names)} resource(s)", data=names)


def _sum_write_chart(args: dict) -> str:
    chart = args.get("chart")
    n_w = len(getattr(chart, "waypoints", []) or [])
    n_l = len(getattr(chart, "legs", []) or [])
    return f"Update the Chart ({n_w} waypoint(s), {n_l} leg(s))"


def _run_write_chart(ctx: ToolContext, args: dict) -> ToolResult:
    chart: Chart = args["chart"]
    vdir = ctx.loaded.vdir
    # Snapshot the prior file for a real undo.
    prior = vdir.chart_file.read_text(encoding="utf-8") if vdir.chart_file.exists() else None

    def undo() -> None:
        if prior is None:
            vdir.chart_file.unlink(missing_ok=True)
        else:
            store._atomic_write(vdir.chart_file, prior)

    store.save_chart(vdir, chart)
    ctx.loaded.chart = store.load_chart(vdir)  # keep the in-memory view resolved & fresh
    return ToolResult(True, _sum_write_chart(args), undo=undo)


def _sum_write_logbook(args: dict) -> str:
    t = args.get("type", "note")
    return f"Append a '{t}' entry to the Logbook"


def _run_write_logbook(ctx: ToolContext, args: dict) -> ToolResult:
    entry = logbook.append(
        ctx.loaded.vdir,
        args.get("body", ""),
        type=args.get("type", "note"),
        by=args.get("by", ctx.by),
        model=args.get("model", ctx.model),
        legs=args.get("legs"),
        now=ctx.now,
    )
    return ToolResult(True, _sum_write_logbook(args), data=entry)  # append-only: no undo


def _sum_run_command(args: dict) -> str:
    return f"Run a shell command: {args.get('command', '')!r}"


def _run_run_command(ctx: ToolContext, args: dict) -> ToolResult:
    # Denied by default policy; only reached if the human explicitly allowed it.
    cmd = args.get("command", "")
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=args.get("timeout", 120))
    ok = proc.returncode == 0
    return ToolResult(ok, f"ran command (exit {proc.returncode})",
                      data={"stdout": proc.stdout, "stderr": proc.stderr,
                            "returncode": proc.returncode})


def _sum_web_fetch(args: dict) -> str:
    return f"Fetch a URL: {args.get('url', '')}"


def _run_web_fetch(ctx: ToolContext, args: dict) -> ToolResult:
    url = args["url"]
    with urllib.request.urlopen(url, timeout=args.get("timeout", 30)) as r:
        body = r.read(args.get("max_bytes", 1_000_000)).decode("utf-8", "replace")
    return ToolResult(True, f"fetched {url}", data=body)


TOOLS: dict[str, Tool] = {
    t.name: t for t in [
        Tool("read_resources", False, False, _sum_read_resources, _run_read_resources),
        Tool("write_chart",    True,  True,  _sum_write_chart,     _run_write_chart),
        Tool("write_logbook",  True,  False, _sum_write_logbook,   _run_write_logbook),
        Tool("run_command",    True,  False, _sum_run_command,     _run_run_command),
        Tool("web_fetch",      False, False, _sum_web_fetch,       _run_web_fetch),
    ]
}


def get_tool(name: str) -> Tool:
    try:
        return TOOLS[name]
    except KeyError:
        raise KeyError(f"unknown tool '{name}'") from None


__all__ = ["Tool", "ToolContext", "ToolResult", "TOOLS", "get_tool"]
