"""Hiedi — HeDE's local-first, cloud-on-consent project-planning assistant.

The layers, in dependency order:

* :mod:`hiedi.core` — pure, Qt-free, bus-free: the Voyage/Chart/Logbook model, the
  on-disk store (+ DAG resolver), the brain router, and the agent engine + permission
  broker. This is the whole unit-test surface.
* :mod:`hiedi.daemon` — ``hiedid``, the session-bus service that owns the router and
  brokers tools; the UI is a thin client.
* :mod:`hiedi.ui` — ``hiedi``, the PySide6 summon panel.
"""

__version__ = "0.1.0"
