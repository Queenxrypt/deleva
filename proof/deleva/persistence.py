"""Lightweight persistence for AutonomousEngine's own continuity state.

Not a database. This exists only to survive process restarts for a small
amount of state: whether a prior execution is still unresolved, when the
last triggered action happened (for backoff), and the activity history. It
sits behind ``EnginePersistence`` so it can be swapped for a real database
later without touching AutonomousEngine.

Never stores secrets: only executionIds, timestamps, and activity event
records (which themselves never carry the KeeperHub API key -- see
deleva.activity.ActivityEvent).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class EnginePersistence(Protocol):
    def load_state(self) -> dict: ...

    def save_state(self, state: dict) -> None: ...


class InMemoryPersistence:
    """Default persistence: lives only for the process lifetime. Used by
    every test and by demo mode so nothing touches disk unless explicitly
    configured to."""

    def __init__(self) -> None:
        self._state: dict = {}

    def load_state(self) -> dict:
        return dict(self._state)

    def save_state(self, state: dict) -> None:
        self._state = dict(state)


class JsonFilePersistence:
    """Simple JSON-file-backed persistence for local/single-process operation.

    Explicitly opt-in -- AutonomousEngine defaults to InMemoryPersistence.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load_state(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def save_state(self, state: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)
