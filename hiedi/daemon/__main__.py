"""Entry point for ``hiedid``."""

from __future__ import annotations

from .service import run


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
