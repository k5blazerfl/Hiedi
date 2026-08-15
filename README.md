# Hiedi

**Hiedi** is [HeDE](https://github.com/k5blazerfl/HeDE)'s local-first, cloud-on-consent
assistant for **building and planning** — and not just software. A kitchen remodel, a
boat build, a thesis, a trip, or a software release are all *Voyages* to Hiedi.

Hiedi is a harbor-pilot sea dragon: she **boards your ship and guides it safely into
port — she never sails it for you.** That character is the product philosophy:

- **The plan is the product, not the chat.** Hiedi maintains a living, user-owned plan;
  chat is just one way to edit it.
- **Local-first, cloud-on-consent.** [Ollama](https://ollama.com) is the default brain —
  private, offline, free. Claude is an optional heavy-reasoning pilot, gated per-Voyage.
  The UI always shows *which brain answered*; nothing leaves the box without consent.
- **Faithful.** Transparent model routing, permissioned agency (a suggest→act dial), and
  reversible, attributed actions. Every change records *who* (`by:`) and *which brain*
  (`model:`).

## The data model — Voyage / Chart / Logbook

Your plans are **plain files you own** (YAML + Markdown), under `~/Voyages/<slug>/`:

```
~/Voyages/backyard-greenhouse/
  voyage.yaml     # the manifest: destination, success criteria, constraints, consent policy
  chart.yaml      # the plan: waypoints (milestones) + legs (tasks), as a DAG
  logbook.md      # append-only dated, attributed narrative: notes, decisions, blockers
  resources/      # attachments, quotes, photos
  .hiedi/
    config.yaml   # model-routing + per-tool permissions for this Voyage
    memory.md     # durable per-Voyage context
```

Greppable, diffable, git-able, hand-editable. No database, no lock-in. See
[`docs/design.md`](docs/design.md).

## Layout

| Layer | What it is |
|---|---|
| `hiedi/core/` | Pure, Qt-free, bus-free. Model, store (+ DAG resolver), logbook, brain router, agent engine + permission broker. The whole test surface. |
| `hiedi/daemon/` | `hiedid` — a per-user session daemon owning `org.hede.hiedi`; routes brains + brokers tools. |
| `hiedi/ui/` | `hiedi` — the PySide6 summon panel: mascot status, Chart, Logbook, a plan-editing compose box, and permission dialogs. |
| `hiedi/cli.py` | `hiedi-voyage` — a headless CLI for the same core (create/list/draft/log). |

## Status

MVP: **Ollama-only** brain; the full **permissioned tool gate**; create a Voyage, have
Hiedi draft an editable Chart, work the plan. The Claude toggle is wired but disabled
(the key will come from HeDE's Keychain over the Secret Service bus). See `docs/design.md`
for what's next.

## Quick start (dev)

```bash
pip install -e '.[dev]'          # pure core + tests, no display/bus needed
pytest                           # the core suite is green without Ollama running

# headless end-to-end (needs a running Ollama):
hiedi-voyage new "Build a backyard greenhouse"
hiedi-voyage draft backyard-greenhouse
hiedi-voyage show  backyard-greenhouse
```
