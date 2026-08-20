"""Bus-free glue that turns model changes into ``Notice`` emissions.

Mirrors :class:`~hiedi.daemon.bridge.PromptBridge`: the service injects an ``emit``
callback (wired to the ``Notice`` D-Bus signal), and this class stays UI-free and
bus-free so the emission + de-dup logic is unit-testable without ``dbus_next``.

Two Notice families are handled differently:

* **Transitions** (leg ready/blocked, waypoint reached) are edge-triggered — computed
  by diffing a before/after Chart, so they're inherently one-shot and always emitted.
* **Standing** notices (arrival, drift, long-lead) are recomputed on every open/sweep,
  so they're de-duplicated by :meth:`Notice.key` within the bridge's lifetime. Acting
  on a Voyage (:meth:`on_mutation`) forgets *its* standing keys, so a condition that a
  mutation clears can legitimately re-surface later if it recurs.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from ..core import notices, store
from ..core.model import Chart
from ..core.notices import Notice
from ..core.store import Clock, today

# emit(kind, voyage, title, body, leg, waypoint) -> None
Emit = Callable[[str, str, str, str, str, str], None]


class NoticeBridge:
    def __init__(self, emit: Emit, *, now: Clock = today) -> None:
        self._emit = emit
        self._now = now
        self._seen: set[str] = set()

    def _emit_all(self, ns: Iterable[Notice], *, dedup: bool) -> int:
        count = 0
        for n in ns:
            if dedup:
                if n.key() in self._seen:
                    continue
                self._seen.add(n.key())
            self._emit(n.kind.value, n.voyage, n.title, n.body,
                       n.leg or "", n.waypoint or "")
            count += 1
        return count

    def on_mutation(self, before: Chart, after: Chart, voyage_id: str) -> int:
        """Emit transitions for a change; forget this Voyage's standing keys."""
        count = self._emit_all(notices.transitions(before, after, voyage_id), dedup=False)
        prefix = f"{voyage_id}:"
        self._seen = {k for k in self._seen if not k.startswith(prefix)}
        return count

    def on_open(self, loaded: store.LoadedVoyage) -> int:
        """Emit a Voyage's standing notices (de-duplicated)."""
        return self._emit_all(notices.standing(loaded, now=self._now), dedup=True)

    def sweep(self, voyages: Iterable[store.VoyageDir] | None = None) -> int:
        """Emit standing notices across all Voyages (the periodic pass)."""
        dirs = list(voyages) if voyages is not None else store.list_voyages()
        return sum(
            self._emit_all(notices.standing(store.open_voyage(d.path), now=self._now),
                           dedup=True)
            for d in dirs
        )

    def forget(self) -> None:
        """Clear all de-dup memory (e.g. on daemon restart semantics in a test)."""
        self._seen.clear()


__all__ = ["NoticeBridge", "Emit"]
