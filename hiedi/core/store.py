"""On-disk store for Voyages — plain YAML + Markdown under ``~/Voyages/<slug>/``.

A thin IO layer over :mod:`hiedi.core.model`. Two things live here that aren't pure
data:

* **Atomic writes** — temp file + ``os.replace`` so a crash never leaves half a file
  (the same discipline as GeST's vault).
* **The DAG resolver** — ``ready`` vs ``blocked`` is *derived* from each leg's ``after``
  deps on load (per data-model Open-Q #1: compute, don't persist stale state).

Timestamps go through an injectable ``now`` clock so tests are deterministic and the
core never reaches for a wall clock implicitly.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from .model import (
    Chart,
    Leg,
    LegStatus,
    Voyage,
    VoyageConfig,
    VoyageStatus,
)

#: The Voyages root — override with ``$HIEDI_VOYAGES`` (honored at call time, so the
#: env var and test reassignment both take effect). Functions default ``root=None`` and
#: fall back to this, rather than binding it as a default argument.
DEFAULT_ROOT = Path(os.environ.get("HIEDI_VOYAGES") or (Path.home() / "Voyages"))

# The four artifacts + the private dir, relative to a Voyage directory.
F_VOYAGE = "voyage.yaml"
F_CHART = "chart.yaml"
F_LOGBOOK = "logbook.md"
D_RESOURCES = "resources"
D_HIEDI = ".hiedi"
F_CONFIG = "config.yaml"
F_MEMORY = "memory.md"

Clock = Callable[[], str]


def today() -> str:
    return date.today().isoformat()


def slugify(title: str) -> str:
    """A filesystem-safe, greppable id from a title."""
    s = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return s or "voyage"


def _atomic_write(path: Path, data: str) -> None:
    """Write ``data`` to ``path`` atomically (temp in the same dir, then replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


def _dump_yaml(obj: dict) -> str:
    return yaml.safe_dump(obj, sort_keys=False, allow_unicode=True, default_flow_style=False)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# --------------------------------------------------------------------------- paths


@dataclass
class VoyageDir:
    """Path helper for one Voyage directory."""

    path: Path

    @property
    def voyage_file(self) -> Path:
        return self.path / F_VOYAGE

    @property
    def chart_file(self) -> Path:
        return self.path / F_CHART

    @property
    def logbook_file(self) -> Path:
        return self.path / F_LOGBOOK

    @property
    def config_file(self) -> Path:
        return self.path / D_HIEDI / F_CONFIG

    @property
    def memory_file(self) -> Path:
        return self.path / D_HIEDI / F_MEMORY

    @property
    def resources_dir(self) -> Path:
        return self.path / D_RESOURCES

    def exists(self) -> bool:
        return self.voyage_file.exists()


# ----------------------------------------------------------------- the DAG resolver


# The "open" states the resolver is allowed to recompute. `active`, `done`, and
# `dropped` are respected as authored — we never un-finish or un-start a leg.
_OPEN = {LegStatus.TODO, LegStatus.READY, LegStatus.BLOCKED}


def _flat(legs: list[Leg]) -> dict[str, Leg]:
    out: dict[str, Leg] = {}
    def walk(ls: list[Leg]) -> None:
        for leg in ls:
            out[leg.id] = leg
            walk(leg.sub)
    walk(legs)
    return out


def resolve(chart: Chart) -> dict[str, LegStatus]:
    """Derive each leg's effective status from its ``after`` dependencies.

    A leg in an *open* state becomes ``ready`` when every ``after`` dep is ``done``,
    else ``blocked``. Legs with no deps are ``ready``. Terminal/active states are
    returned unchanged. Unknown dep ids are treated as not-done (safer: stays blocked).
    """
    flat = _flat(chart.legs)
    result: dict[str, LegStatus] = {}
    for leg_id, leg in flat.items():
        if leg.status not in _OPEN:
            result[leg_id] = leg.status
            continue
        unmet = [d for d in leg.after
                 if d not in flat or flat[d].status is not LegStatus.DONE]
        result[leg_id] = LegStatus.BLOCKED if unmet else LegStatus.READY
    return result


def apply_resolution(chart: Chart) -> Chart:
    """Mutate the chart's legs to their derived ready/blocked status, in place."""
    derived = resolve(chart)
    for leg_id, leg in _flat(chart.legs).items():
        leg.status = derived[leg_id]
    return chart


# --------------------------------------------------------------- create / load / save


def create_voyage(
    title: str,
    *,
    root: Path | None = None,
    destination: str = "",
    kind: str = "build",
    success: list[str] | None = None,
    now: Clock = today,
) -> VoyageDir:
    """Write a fresh Voyage skeleton and return its directory handle.

    Raises :class:`FileExistsError` if the slug is already taken (never clobbers).
    """
    root = Path(root) if root is not None else DEFAULT_ROOT
    slug = slugify(title)
    vdir = VoyageDir(Path(root) / slug)
    if vdir.exists():
        raise FileExistsError(f"a Voyage already exists at {vdir.path}")

    stamp = now()
    voyage = Voyage(
        id=slug, title=title, kind=kind,
        destination=destination or title,
        success=list(success or []),
        status=VoyageStatus.PLANNING,
        created=stamp, updated=stamp,
    )
    vdir.resources_dir.mkdir(parents=True, exist_ok=True)
    save_voyage(vdir, voyage)
    save_chart(vdir, Chart())
    save_config(vdir, VoyageConfig())
    _atomic_write(vdir.logbook_file,
                  f"# Logbook — {title}\n\n"
                  f"## {stamp} · milestone · by:hiedi\n"
                  f"Voyage created. Destination set. Ready to chart the route.\n")
    _atomic_write(vdir.memory_file, f"# Hiedi memory — {title}\n\n")
    return vdir


def save_voyage(vdir: VoyageDir, voyage: Voyage, *, now: Clock | None = None) -> None:
    if now is not None:
        voyage.updated = now()
    _atomic_write(vdir.voyage_file, _dump_yaml(voyage.to_dict()))


def save_chart(vdir: VoyageDir, chart: Chart) -> None:
    _atomic_write(vdir.chart_file, _dump_yaml(chart.to_dict()))


def save_config(vdir: VoyageDir, config: VoyageConfig) -> None:
    _atomic_write(vdir.config_file, _dump_yaml(config.to_dict()))


def load_voyage(vdir: VoyageDir) -> Voyage:
    return Voyage.from_dict(_load_yaml(vdir.voyage_file))


def load_chart(vdir: VoyageDir, *, resolved: bool = True) -> Chart:
    chart = Chart.from_dict(_load_yaml(vdir.chart_file))
    if resolved:
        apply_resolution(chart)
    return chart


def load_config(vdir: VoyageDir) -> VoyageConfig:
    return VoyageConfig.from_dict(_load_yaml(vdir.config_file))


@dataclass
class LoadedVoyage:
    """Everything for one Voyage, loaded together (chart already DAG-resolved)."""

    vdir: VoyageDir
    voyage: Voyage
    chart: Chart
    config: VoyageConfig


def open_voyage(path: Path | str) -> LoadedVoyage:
    vdir = VoyageDir(Path(path))
    if not vdir.exists():
        raise FileNotFoundError(f"no Voyage at {vdir.path}")
    return LoadedVoyage(vdir, load_voyage(vdir), load_chart(vdir), load_config(vdir))


def find_voyage(ref: str, *, root: Path | None = None) -> LoadedVoyage:
    """Open a Voyage by slug (under ``root``) or by an explicit path."""
    root = Path(root) if root is not None else DEFAULT_ROOT
    p = Path(ref)
    if p.is_dir():
        return open_voyage(p)
    return open_voyage(Path(root) / slugify(ref))


def list_voyages(root: Path | None = None) -> list[VoyageDir]:
    root = Path(root) if root is not None else DEFAULT_ROOT
    if not Path(root).is_dir():
        return []
    dirs = [VoyageDir(p) for p in sorted(Path(root).iterdir()) if p.is_dir()]
    return [d for d in dirs if d.exists()]


__all__ = [
    "DEFAULT_ROOT", "Clock", "today", "slugify",
    "VoyageDir", "LoadedVoyage",
    "resolve", "apply_resolution",
    "create_voyage", "save_voyage", "save_chart", "save_config",
    "load_voyage", "load_chart", "load_config",
    "open_voyage", "find_voyage", "list_voyages",
]
