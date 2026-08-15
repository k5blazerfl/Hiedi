"""``hiedi`` — the PySide6 summon panel.

For the MVP the UI drives the engine **in-process** (:class:`~hiedi.ui.backend.InProcessBackend`)
so it runs with only PySide6 + a local Ollama — no session bus required. The seam is an
abstract backend, so a ``DBusBackend`` talking to ``hiedid`` drops in later without the
widgets changing. Permission prompts reuse the same :class:`~hiedi.daemon.bridge.PromptBridge`
the daemon uses, so a worker-thread ask marshals cleanly to a GUI-thread dialog.
"""
