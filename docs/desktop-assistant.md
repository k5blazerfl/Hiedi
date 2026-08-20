# Design: Hiedi as a HeDE desktop assistant

*Status: design · Scope: how Hiedi presents herself on the HeDE desktop — a
graduated, opt-out companion ("Clippy done right") layered over the existing
`org.hede.hiedi` daemon, plus the fresh-install onboarding guide · Depends on:
the daemon signals (`Status`/`Token`/`AskPermission`), `layer-shell-qt:6`, HeDE's
bar exposing an applet slot, the seed-300 mascot art from `~/hiedi-lab` · Defers:
the `Notice` signal + `presence.yaml` wire-up (P1 build), the applet-slot contract
spec, system-wide (non-Voyage) notifications · Milestone: after the MVP core;
ships alongside the shell as a lean, GPU-free layer.*

## 1. The idea

Hiedi is a desktop assistant in the lineage of the Office Assistant — a companion
that can greet you, guide you, and surface help — but built so the thing people
*hated* about Clippy is impossible by construction. The rule that makes that true:

> **Presence never gates capability.** The character is a *skin* over the engine.
> Everything Hiedi can do is reachable with the character invisible — the summon
> panel (`hiedi/ui/app.py`), the `hiedi-voyage` CLI, a hotkey, and plain toasts.
> Turning the dog down never costs you function; the "cut to the chase" user and
> the "I love the companion" user run the same engine.

## 2. The boundary that matters: shell vs. brain

The real reason Hiedi is separable is **not** the character — it's the **AI**. A
local LLM wants a GPU and disk that most people don't have or want. So the cut
runs *inside* Hiedi, not around it:

| Layer | What | Weight | Integration |
|---|---|---|---|
| **Shell** | `core` + `hiedid` + companion/applet/panel + CLI + **all Notices** | Lean — PySide6, PyYAML, dbus-next, layer-shell-qt. **No Ollama.** | The close-Helm citizen; ships default-on. |
| **Local brain** | Ollama runtime + model + the *draft / revise / chat* verbs | Heavy — GPU/LLM userspace | Behind `hiedi[ai]`, default **off**. |
| **Cloud brain** | Claude, per-Voyage consent, Keychain key | Zero local hardware | Already gated; orthogonal. |

The unlock: **the entire companion and every plan-state Notice run on the pure,
Qt-free `core` with zero AI** — Leg ready/blocked, Waypoint reached, drift, and
long-lead reminders are all deterministic DAG + date math. Only three verbs need a
brain: **draft, revise, chat**.

- **Packaging:** one `gui-apps/hiedi` package; the AI stack sits behind a
  `hiedi[ai]` USE flag (default off). Without it the Ollama/model closure never
  exists → a lean base ISO and binhost exclusion for free. Enabling is a
  `USE=ai` re-emerge — no repo change, the shell keeps running throughout.
- **Manual mode is first-class, not degraded.** With no brain, Hiedi is a full
  structured planner + desktop companion; she just doesn't draft/chat. The AI
  verbs are shown **absent, not stubbed**. A GPU upgrades a good planner into a
  drafting one; it is never the price of entry.
- **Presence-level and brain-presence are independent dials.** *First Mate with
  no brain* (a chatty hand-planning companion) and *On Watch with a brain* (a
  silent applet that drafts on demand) are both valid.

## 3. The presence ladder

One slider (Settings → Hiedi → Presence, with a live preview) plus quick-controls
in the mascot's right-click menu (*Quiet down* / *Send below deck* / *Do Not
Disturb*). **Default: On Watch.**

| Tier | Name | What you get |
|---|---|---|
| **0** | **On Watch** *(default)* | A first-class **bar applet**: a pin in HeDE's one bar. Left-click → a pullout (status + recent Notices + a compose line + *Open panel*); right-click → a jump-list menu; Notices arrive as the bar's bottom-right toasts; the pin itself **breathes** with the `Status` signal. No floating character. |
| **1** | **On Deck** | An ambient layer-shell floater resting in a corner, click-through when idle, pose = live status. Still never speaks first. |
| **2** | **At Your Side** | On Deck **+ proactive speech bubbles** for Notices — the true companion tier, governed by the interruption budget (§6). |
| **3** | **First Mate** | + idle animation, personality lines, optional sound. |

"Fully off" is not a separate rung — it's just **unpinning the applet**, exactly
like any other applet.

## 4. Bar integration — an applet, not a tray

HeDE has **no system tray** (`hede-theme.md`): applets (wifi, sound, battery,
notifications…) live as **pins** in the one glass bar alongside apps, and only the
clock is anchored. What "system programs" get that ordinary apps don't is the
**pullout** (a surface that emerges from behind the bar) and persistent
pin-stream residency. Hiedi is one of those: her pin opens a pullout, not just a
window.

**Dependency direction is one-way.** HeDE's bar publishes a generic **applet-slot
contract**; Hiedi *provides* an applet that fills it when installed. The panel
never imports Hiedi; uninstalling Hiedi leaves HeDE unchanged. This is the same
pattern Flotilla/Customs use to give VMs "real taskbar identity" — a contract, not
a hard dependency. `gui-apps/hede` therefore never RDEPENDs on Hiedi; the shell is
reached only through a (default-on, off-able) `hede[hiedi]` USE flag.

## 5. Fresh install — the Orientation guide

On a new install Hiedi is **visible and acts as an opt-out feature guide**
("Orientation"), then settles to the On Watch default. Orientation is not a tier —
it's a cross-cutting first-run overlay with elevated presence (a welcome pullout /
gentle guided steps).

**The guide *is* a Voyage.** It ships as a pre-authored "Get to Know HeDE" Voyage
(`hiedi/data/voyages/get-started/`) and is piloted through the exact
Voyage/Chart/Logbook machinery. Consequences:

- **Zero brain.** A shipped Chart + the DAG resolver is the whole tour; it runs
  identically on a potato and a workstation. `cloud: never`.
- **Resumable.** Progress is the logbook — dismiss at step 4, return next week, it
  remembers.
- **It demos the product.** You learn the desktop *and* learn what a Voyage is, in
  one motion.

On first login the shell copies the template into `~/Voyages/get-started/` (so the
user owns their copy and their edits) and opens it in Orientation.

**Two distinct opt-outs — don't conflate them:**

- **Opt out of the guide** — "No thanks, I know my way around." She stops guiding
  and settles to silent On Watch. This is the front-and-center first choice.
- **Opt out of Hiedi entirely** — unpin the applet / disable `hede[hiedi]`. Plain
  lean desktop.

**First-run guardrails (this is the Clippy danger zone):** the very first
interaction *is* the decline prompt (never auto-launched pop-ups); the tour is
user-paced (Next / Skip), dismissible at every step, and **one-time** — once
completed or declined she never re-nags; the offer lives quietly in her menu.

The tour's own content teaches the opt-out (`adjust-hiedi` leg) — a good guide
shows you how to dismiss the guide.

## 6. Steady-state Notices — **Voyage-only** for v1

After onboarding, what may Hiedi surface unprompted? **Only things about your
plans.** She does not annex system notifications — HeDE's own toasts own "battery
low", "update available", and the rest. The `Notice` source list is a registry, so
widening to system-wide later just registers more sources; v1 ships the plan
sources only.

All of these are computed by the pure `core` — **no brain required**:

| Notice | Trigger (deterministic) |
|---|---|
| **Leg ready** | a Leg's `after` deps all reached `done` → newly actionable |
| **Waypoint reached** | all legs under a Waypoint `done` (`newly_completed_waypoints`) |
| **Blocker** | a Leg transitioned to `blocked` |
| **Long-lead reminder** | a Leg with `needs[]` whose downstream Waypoint `target` date requires ordering now (date math) |
| **Drift** | an `active` Voyage with no logbook entry in N days |
| **Draft done / Arrival** | a draft finished (brain) · a Voyage reached `arrived` |

**Presentation follows the tier:** On Watch → toast + breathing pin; On Deck →
pose change, no bubble; At Your Side / First Mate → a speech bubble.

**Interruption budget (tiers 2–3):** an hourly cap; focus- and fullscreen-aware
(never over a presentation, never steals focus); a Do-Not-Disturb window;
per-kind mutes; severity gating (only the plan events above — never idle chatter);
every proactive surface is dismissible and "mute this kind"-able. She only ever
*suggests* — a bubble is the suggestion, your click is the act, fail-closed, the
same posture as the tool-permission broker and the harbor-pilot persona.

## 7. Architecture deltas

- **`hiedi-companion`** — a lightweight client that subscribes to `org.hede.hiedi`
  and renders the mascot. Tray-pin, ambient floater, and bubbles are render modes
  of this one client, selected by the presence dial. The summon panel is untouched.
- **New signal `Notice(kind, title, body, voyage, action)`** on the daemon — the
  engine's channel for "something worth surfacing happened," rendered per tier.
- **`~/.config/hiedi/presence.yaml`** — `level`, `dnd`, `hourly_cap`, per-kind
  mutes. A desktop preference, so it's global (not per-Voyage).
- **Reuse:** seed-300 GSD poses from `~/hiedi-lab` (idle/thinking/success/concern
  already mapped in `hiedi/ui/mascot.py`); a 24px pin silhouette; `layer-shell-qt`
  for the floater/bubbles.

## 8. Why this isn't hated-Clippy

| Clippy's sin | Structural answer |
|---|---|
| On + chatty by default | default is silent On Watch; bubbles are opt-in at tier 2 |
| Interrupted your work | interruption budget: cap, focus/fullscreen-aware, never steals focus |
| Couldn't dismiss it | one-click *Send below deck*; two clean opt-outs; DND from her menu |
| Useless guesses | Notices are event-driven from real Chart-DAG state, not guesses; each kind mutable |
| Blocked the UI | ambient/bubbles are click-through, never modal (only the permission dialog is, deliberately) |
| Acted on its own | she only suggests; the click is the act, fail-closed |

## 9. Phasing

- **P1 — Presence spine:** `presence.yaml` + the dial; refactor `mascot.py`'s pose
  rendering into a reusable presence surface; the `Notice` signal + the
  toast route; ship **On Watch** and the Orientation guide. (Delivers the baseline
  + onboarding with zero Clippy risk.)
- **P2 — On Deck:** the layer-shell ambient floater driven by `Status`;
  click-through idle; the face right-click quick-controls + DND.
- **P3 — At Your Side:** speech bubbles for `Notice`/`AskPermission`; the
  interruption budget; per-kind mutes; the focus/DND guard.
- **P4 — First Mate:** idle animation, personality lines, optional sound.

Each phase is independently shippable and every higher rung is pure addition — a
bug at First Mate can never regress the "she's gone but everything works" promise.

## 10. Shipped in the introducing commit

- This document.
- The **"Get to Know HeDE" onboarding Voyage** template
  (`hiedi/data/voyages/get-started/{voyage.yaml,chart.yaml,logbook.md}`) — a
  schema-valid, brain-free, `cloud: never` Chart: 6 Waypoints (Welcome Aboard →
  Find Your Way Around → Make It Yours → Get Things Done → Meet Your Pilot →
  You're Underway) / 16 Legs, with the Hiedi opt-out taught as a first-class step
  and a parallel-ready DAG.
- The `pyproject.toml` package-data glob widened to ship the template.

Everything in §7 (the `Notice` signal, `presence.yaml`, `hiedi-companion`) is P1
build work that follows.
