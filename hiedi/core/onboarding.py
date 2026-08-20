"""First-login seeding of the "Get to Know HeDE" onboarding Voyage.

The shell calls :func:`seed_onboarding` on first login: it copies the packaged
template (``hiedi/data/voyages/get-started/``) into the user's Voyages root so they
**own their copy** and their edits, and stamps the opening ``cast off`` logbook
entry. Idempotent — a returning user is never re-seeded (their progress, and any
edits, survive). Pure + brain-free; see ``docs/desktop-assistant.md`` §5.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from . import logbook, store
from .model import Consent, VoyageConfig
from .store import Clock, VoyageDir, today

ONBOARDING_ID = "get-started"


def _template():
    """The packaged template directory (a Traversable)."""
    return resources.files("hiedi.data").joinpath("voyages", ONBOARDING_ID)


def is_seeded(root: Path | None = None) -> bool:
    """True if the onboarding Voyage already exists under ``root``."""
    base = Path(root) if root is not None else store.DEFAULT_ROOT
    return VoyageDir(base / ONBOARDING_ID).exists()


def seed_onboarding(
    root: Path | None = None,
    *,
    now: Clock = today,
    force: bool = False,
) -> VoyageDir | None:
    """Copy the template into ``root`` and stamp the opening entry.

    Returns the new :class:`VoyageDir`, or ``None`` if it already existed (unless
    ``force``, which reseeds from the template — discarding the user's copy).
    """
    base = Path(root) if root is not None else store.DEFAULT_ROOT
    vdir = VoyageDir(base / ONBOARDING_ID)
    if vdir.exists() and not force:
        return None

    src = _template()
    vdir.path.mkdir(parents=True, exist_ok=True)
    vdir.resources_dir.mkdir(parents=True, exist_ok=True)

    # The user-owned manifest + plan come straight from the template.
    for name in (store.F_VOYAGE, store.F_CHART):
        (vdir.path / name).write_text(
            src.joinpath(name).read_text(encoding="utf-8"), encoding="utf-8")

    # A per-Voyage config that matches the manifest's local-only stance.
    store.save_config(vdir, VoyageConfig(cloud=Consent.NEVER))
    vdir.memory_file.parent.mkdir(parents=True, exist_ok=True)
    vdir.memory_file.write_text("# Hiedi memory — Get to Know HeDE\n\n", encoding="utf-8")

    # Seed the logbook with the template preamble, then stamp the cast-off entry.
    preamble = src.joinpath(store.F_LOGBOOK).read_text(encoding="utf-8").rstrip() + "\n"
    vdir.logbook_file.write_text(preamble, encoding="utf-8")
    logbook.append(
        vdir,
        "Welcome aboard — your HeDE tour is under way. Skip or resume anytime.",
        type="milestone", by="hiedi", now=now)
    return vdir


__all__ = ["ONBOARDING_ID", "is_seeded", "seed_onboarding"]
