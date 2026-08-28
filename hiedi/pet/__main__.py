"""``python -m hiedi.pet`` — run the desktop-pet bridge."""

from __future__ import annotations

from .bridge import run

if __name__ == "__main__":
    raise SystemExit(run())
