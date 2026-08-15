"""``hiedi-voyage`` — a headless CLI over the pure core.

The same engine the daemon/UI drive, wired to a real Ollama brain and a console
permission asker. Handy for scripting and for the end-to-end verification path without
a display or a session bus.

    hiedi-voyage new "Build a backyard greenhouse" --success "Frame level" --success "Under budget"
    hiedi-voyage draft backyard-greenhouse
    hiedi-voyage show  backyard-greenhouse
    hiedi-voyage done  backyard-greenhouse measure
    hiedi-voyage log   backyard-greenhouse "Pad is 4cm out of level" --type blocker
"""

from __future__ import annotations

import argparse
import sys

from .core import logbook, store
from .core.agent import AgentEngine
from .core.agent.permissions import Decision, ToolRequest
from .core.brain import OllamaBrain, Router


def _console_asker(req: ToolRequest) -> Decision:
    rev = "reversible" if req.reversible else "NOT reversible"
    sys.stderr.write(f"\n  Hiedi wants to: {req.summary}\n"
                     f"  (tool: {req.tool}, {rev})\n")
    try:
        ans = input("  Allow? [y]es once / [s]ession / [N]o: ").strip().lower()
    except EOFError:
        ans = ""
    if ans in ("y", "yes"):
        return Decision.ALLOW_ONCE
    if ans in ("s", "session"):
        return Decision.ALLOW_SESSION
    return Decision.DENY


def _engine() -> AgentEngine:
    router = Router(OllamaBrain())
    return AgentEngine(router, asker=_console_asker)


def _status_glyph(status: str) -> str:
    return {"done": "✓", "ready": "○", "blocked": "×", "active": "▸",
            "dropped": "–", "todo": "·"}.get(status, "·")


def cmd_new(args) -> int:
    vdir = store.create_voyage(
        args.title, destination=args.destination or args.title,
        kind=args.kind, success=args.success or [])
    print(f"Created Voyage '{vdir.path.name}' at {vdir.path}")
    return 0


def cmd_list(args) -> int:
    dirs = store.list_voyages()
    if not dirs:
        print("No Voyages yet. Try: hiedi-voyage new \"...\"")
        return 0
    for d in dirs:
        v = store.load_voyage(d)
        print(f"  {d.path.name:30}  {v.status.value:10}  {v.title}")
    return 0


def cmd_show(args) -> int:
    loaded = store.find_voyage(args.voyage)
    v, c = loaded.voyage, loaded.chart
    print(f"# {v.title}  [{v.status.value}]  brain-default: {loaded.config.routing.default}")
    print(f"  Destination: {v.destination}")
    if v.success:
        print("  Success:", "; ".join(v.success))
    for wp in c.waypoints:
        tgt = f" (target {wp.target})" if wp.target else ""
        print(f"\n  ⚓ {wp.title}{tgt}")
        for leg in [l for l in c.legs if l.waypoint == wp.id]:
            who = f" by:{leg.by}" if leg.by else ""
            print(f"     {_status_glyph(leg.status.value)} [{leg.id}] {leg.title}{who}")
    loose = [l for l in c.legs if not any(l.waypoint == w.id for w in c.waypoints)]
    for leg in loose:
        print(f"     {_status_glyph(leg.status.value)} [{leg.id}] {leg.title}")
    return 0


def cmd_draft(args) -> int:
    loaded = store.find_voyage(args.voyage)
    print(f"Asking the {loaded.config.routing.default} brain to draft a Chart...")
    res = _engine().draft_chart(loaded)
    print(f"  brain: {res.decision.brain} ({res.decision.model}) — {res.decision.reason}")
    print(f"  {res.message}")
    if res.milestones:
        print(f"  milestones reached: {', '.join(res.milestones)}")
    return 0 if res.applied else 1


def cmd_done(args) -> int:
    loaded = store.find_voyage(args.voyage)
    res = _engine().toggle_leg(loaded, args.leg, done=not args.undo)
    print(f"  {res.message}")
    if res.milestones:
        print(f"  milestones reached: {', '.join(res.milestones)}")
    return 0 if res.applied else 1


def cmd_log(args) -> int:
    loaded = store.find_voyage(args.voyage)
    entry = logbook.append(loaded.vdir, args.body, type=args.type, by="user",
                           legs=args.leg or [])
    print(f"  logged {entry.type} entry.")
    return 0


def cmd_logbook(args) -> int:
    loaded = store.find_voyage(args.voyage)
    for e in logbook.load(loaded.vdir):
        model = f" model:{e.model}" if e.model else ""
        links = f"  → {' '.join('['+l+']' for l in e.legs)}" if e.legs else ""
        print(f"{e.date} · {e.type} · by:{e.by}{model}\n  {e.body}{links}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hiedi-voyage", description="Plan a Voyage with Hiedi.")
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="create a Voyage")
    n.add_argument("title")
    n.add_argument("--destination", default="")
    n.add_argument("--kind", default="build")
    n.add_argument("--success", action="append", help="a success criterion (repeatable)")
    n.set_defaults(func=cmd_new)

    sub.add_parser("list", help="list Voyages").set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="show a Voyage's Chart")
    s.add_argument("voyage")
    s.set_defaults(func=cmd_show)

    d = sub.add_parser("draft", help="have Hiedi draft the Chart")
    d.add_argument("voyage")
    d.set_defaults(func=cmd_draft)

    dn = sub.add_parser("done", help="mark a Leg done (or --undo to reopen)")
    dn.add_argument("voyage")
    dn.add_argument("leg")
    dn.add_argument("--undo", action="store_true")
    dn.set_defaults(func=cmd_done)

    lg = sub.add_parser("log", help="append a Logbook entry")
    lg.add_argument("voyage")
    lg.add_argument("body")
    lg.add_argument("--type", default="note",
                    choices=["note", "decision", "progress", "blocker", "milestone"])
    lg.add_argument("--leg", action="append", help="link a Leg id (repeatable)")
    lg.set_defaults(func=cmd_log)

    lb = sub.add_parser("logbook", help="print the Logbook")
    lb.add_argument("voyage")
    lb.set_defaults(func=cmd_logbook)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FileExistsError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
