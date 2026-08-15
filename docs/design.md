# Hiedi — design

Hiedi is HeDE's local-first, cloud-on-consent assistant for **building and planning**,
for anything — not just software. This document is the single source of truth for the
data model and the architecture. The data model was first drafted as
`voyage-data-model.md` v0.1 and is promoted here.

## 1. Philosophy → structure

Hiedi is a harbor pilot: she boards your ship and guides it into port; she never sails it
for you. Three commitments, and how each is made *structural* rather than a promise:

| Commitment | How it's enforced in the design |
|---|---|
| **The plan is the product, not the chat.** | The durable artifact is a *Voyage* on disk (YAML+MD). Chat is one editor of it; the UI is a view over the files. |
| **Local-first, cloud-on-consent.** | The `Router` defaults to Ollama. The cloud brain is unreachable past a per-Voyage `cloud` gate; the reply carries `brain`/`model` so the UI always shows who answered. |
| **Faithful (suggest→act dial).** | Every effect goes through one `Tool`, gated by the `PermissionBroker` (deny/ask/allow), applied reversibly, and stamped `by:`/`model:`. The default asker **fails closed**. |

## 2. Data model — Voyage / Chart / Logbook

A Voyage is a directory (default `~/Voyages/<slug>/`, override with `$HIEDI_VOYAGES`):

```
~/Voyages/backyard-greenhouse/
  voyage.yaml     # manifest: destination, success criteria, constraints, consent policy
  chart.yaml      # the plan: waypoints (milestones) + legs (tasks), a DAG
  logbook.md      # append-only dated, attributed narrative
  resources/      # attachments
  .hiedi/
    config.yaml   # routing + per-tool permissions for this Voyage
    memory.md     # durable per-Voyage context (next milestone)
```

* **Voyage** (`voyage.yaml`) — `destination`, `success[]`, `constraints`, `status`
  (`planning·active·paused·arrived·abandoned`), `cloud` consent (`never·ask·allow`).
* **Chart** (`chart.yaml`) — `waypoints[]` (ordered milestones) + `legs[]` (tasks). A Leg
  names its `waypoint`, its `after[]` dependencies (the DAG edges), what it `needs[]`
  (materials/tools/info) and `produces[]`, and may nest `sub[]`. Leg status is
  `todo·ready·active·blocked·done·dropped`.
* **Logbook** (`logbook.md`) — dated, attributed, typed entries
  (`note·decision·progress·blocker·milestone`), linking legs by `[id]`.

**`ready`/`blocked` is derived, not stored** (data-model Open-Q #1): `store.resolve()`
computes it from `after` on load. A leg in an *open* state (`todo/ready/blocked`) becomes
`ready` when every dep is `done`, else `blocked`; `active/done/dropped` are respected as
authored. A **milestone** entry is auto-written when a Waypoint's legs all reach `done`
(`logbook.newly_completed_waypoints`).

Everything is plain YAML+MD: greppable, diffable, git-able, hand-editable. Serialization
is tolerant — unknown keys are ignored, empties omitted — so hand-edits round-trip.

## 3. Architecture — three layers

Mirrors GeST's core/daemon/frontend discipline, but session-scoped (no root, no polkit).

```
        hiedi (PySide6 UI)            hiedi-voyage (CLI)
                \                        /
             Backend seam        (engine direct)
                  \                    /
   hiedid  ──────  AgentEngine  ──────  (in-process for MVP)
 (org.hede.hiedi)      │
                       ├── Router ──── OllamaBrain (local, default)
                       │          └── ClaudeBrain (cloud, gated; stub)
                       └── PermissionBroker ── Tool registry ── store / logbook
```

### `hiedi/core/` — pure, Qt-free, bus-free (the whole test surface)
* `model.py` — the dataclasses + enums above.
* `store.py` — directory layout, **atomic writes** (temp + `os.replace`), the **DAG
  resolver**, load/save, `$HIEDI_VOYAGES`-configurable root.
* `logbook.py` — append/parse, milestone-transition detection.
* `brain/` — `Brain` protocol; `OllamaBrain` (stdlib `urllib` → `/api/chat`, injectable
  transport); `ClaudeBrain` (stub; key comes from Secret Service — see §5); `Router`
  (chooses brain, enforces the consent gate, falls back to local on cloud failure).
* `agent/` — `permissions.py` (`PermissionBroker`, deny/ask/allow, session grants,
  fail-closed default asker); `tools.py` (the five tools, each declaring mutates/
  reversible + an `undo`); `prompts.py` (persona + strict-JSON chart drafting + tolerant
  parse); `engine.py` (the loop: draft/toggle/chat; one gated, attributed write path).

### `hiedi/daemon/` — `hiedid`, the session service
Owns the router + engine + active-Voyage state and exports `org.hede.hiedi` on the
session bus (dbus-next), following HeDE Keychain's vault+daemon shape. Blocking engine
calls run in a thread-pool executor; permission asks marshal to the UI via `PromptBridge`
(a bus-free, unit-tested async↔sync reconciler) which emits `AskPermission` and blocks the
worker until `RespondPermission`, timing out **closed**. Signals: `Status`
(idle·thinking·success·concern → mascot poses), `Token` (streaming), `AskPermission`.

### `hiedi/ui/` — `hiedi`, the summon panel (PySide6)
A `Backend` seam (`InProcessBackend` now; a `DBusBackend` later) so widgets don't change
when the bus is added. Widgets: `MascotWidget` (pose = live status), `ChartView`
(waypoints→legs, checkable, blocked dimmed), `LogbookView`, `PermissionDialog` (allow
once / allow this Voyage / deny), a compose box. Engine work runs on a `QThread`; asks
reuse `PromptBridge` so a worker-thread ask becomes a GUI-thread dialog.

## 4. MVP scope (this release)

**Ollama-only** brain; the **full permissioned tool gate**. Create a Voyage → Hiedi
drafts an editable Chart → work the plan (check off Legs, DAG-derived ready/blocked, auto
milestones) → all as plain YAML+MD. Runnable three ways: the summon panel (in-process),
the `hiedi-voyage` CLI, and — once `dbus-next` is installed — `hiedid` + a bus client.

## 5. What's next (wired, not yet on)

* **Claude brain.** `ClaudeBrain` is wired into the router but disabled. Enabling it is
  (a) implement the Anthropic Messages API call, (b) resolve the key via **Keychain over
  the Secret Service session bus** (`org.freedesktop.secrets`, lookup attributes
  `{service: anthropic, purpose: hiedi-cloud-brain}`) — the daemon injects the resolver so
  the core never imports a bus binding. The per-Voyage `cloud` gate already governs it.
* **Conversational plan editing.** The compose box currently drives drafting; the `chat`
  verb is read-only. Next: let a chat turn propose Chart edits routed through `write_chart`.
* **`.hiedi/memory.md` retrieval** into the prompt for durable per-Voyage context.
* **HeDE integration.** Autostart `hiedid` in the session; a layer-shell dock summon;
  labelled mascot poses from `~/hiedi-lab`; a 24px systray silhouette.
* **`run_command` / `web_fetch`** exist and are gated (deny/ask) but aren't yet surfaced
  as agent-initiated steps in the UI.

## 6. Packaging

Amphitheater `gui-apps/hiedi` — a live `hiedi-9999` git-r3 ebuild first, release
ebuild+Manifest at first tag (the `gui-apps/hede` flow). RDEPEND `dev-python/pyside:6`,
`dev-python/pyyaml`, `dev-python/dbus-next`, `gui-libs/layer-shell-qt:6`. Ollama is a
documented runtime service, not a hard dep; the (future) Claude key path expects a running
Secret Service provider (HeDE's Keychain / `keyringd`).
