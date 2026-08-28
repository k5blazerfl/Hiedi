"""Hiedi's desktop-pet embodiment — the brain↔body bridge.

The pet (xpet today, a native ``helm-pet`` layer-shell surface tomorrow) is Hiedi's
face on the desktop, replacing the Qt companion window. :mod:`hiedi.pet.channel` writes
``say`` / ``mood`` commands to the pet's control FIFO; :mod:`hiedi.pet.bridge` subscribes
to the ``org.hede.hiedi`` daemon and translates its Status/Say signals into those
commands. The wire is runtime-agnostic, so swapping the body for the Wayland-native
pet later touches neither the brain nor this package.
"""

from .channel import PetChannel, default_path

__all__ = ["PetChannel", "default_path"]
