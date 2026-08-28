"""The pet's control channel — write ``say`` / ``mood`` / ``quit`` to xpet's FIFO.

The desktop pet (xpet, and later the native ``helm-pet``) opens a line-delimited
control FIFO and drives its speech bubble + mood from it. This is the Python end of
that wire: the Hiedi brain's voice and status become one-line commands the pet reads.

Runtime-agnostic and display-free, so it unit-tests without a pet or a bus. Writes are
non-blocking and *forgiving*: if the pet isn't running (no FIFO, or no reader on it),
the write is dropped and ``False`` returned rather than raising — the brain should never
stall or crash because its body is asleep.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path


def default_path() -> Path:
    """Where xpet listens for commands — mirror its own resolution order.

    ``$XDG_RUNTIME_DIR/hiedi-pet.ctl``, falling back to ``/tmp/hiedi-pet-<uid>.ctl``.
    """
    rt = os.environ.get("XDG_RUNTIME_DIR")
    if rt:
        return Path(rt) / "hiedi-pet.ctl"
    return Path(f"/tmp/hiedi-pet-{os.getuid()}.ctl")


def event_default_path() -> Path:
    """Where the pet reports interactions (``poke`` …) — the brain reads this.

    ``$XDG_RUNTIME_DIR/hiedi-pet.evt``, falling back to ``/tmp/hiedi-pet-<uid>.evt``.
    """
    rt = os.environ.get("XDG_RUNTIME_DIR")
    if rt:
        return Path(rt) / "hiedi-pet.evt"
    return Path(f"/tmp/hiedi-pet-{os.getuid()}.evt")


def _one_line(text: str) -> str:
    """Collapse whitespace/newlines — the protocol is one command per line."""
    return " ".join(text.split())


class PetChannel:
    """A thin writer over the pet's control FIFO."""

    def __init__(self, path: os.PathLike[str] | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_path()

    def _write(self, line: str) -> bool:
        data = (line.rstrip("\n") + "\n").encode("utf-8", "replace")
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
        except FileNotFoundError:
            return False  # no FIFO — the pet isn't running
        except OSError as e:
            if e.errno == errno.ENXIO:
                return False  # FIFO exists but nobody's reading (pet down)
            raise
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        return True

    def say(self, text: str) -> bool:
        """Show ``text`` in the pet's speech bubble (dropped if empty)."""
        text = _one_line(text)
        return self._write(f"say {text}") if text else False

    def mood(self, mood: str) -> bool:
        """Set the pet's mood pose (``idle`` / ``happy`` / ``sleeping``)."""
        return self._write(f"mood {mood}")

    def notify(self, text: str) -> bool:
        """Present ``text`` as a standalone notification card + run-in choreography."""
        text = _one_line(text)
        return self._write(f"notify {text}") if text else False

    def quit(self) -> bool:
        """Ask the pet to exit."""
        return self._write("quit")


__all__ = ["PetChannel", "default_path", "event_default_path"]
