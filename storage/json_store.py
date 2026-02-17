"""Abstract base class for thread-safe, atomic JSON file stores."""

from __future__ import annotations

import json
import threading
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class JsonFileStore(ABC):
    """Thread-safe, atomic JSON file store base class.

    Provides:
    - Thread-safe lazy loading with a lock
    - Atomic write (temp file + rename) to prevent corruption
    - UUID-based ID generation
    - Reload support for picking up external changes
    """

    def __init__(self, resources_path: Path, filename: str) -> None:
        """
        Initialize the store.

        Args:
            resources_path: Path to the resources directory
            filename: Name of the JSON file (e.g., 'benders.json')
        """
        self._resources_path = resources_path
        self._file_path = resources_path / filename
        self._loaded = False
        self._load_lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        """Thread-safe lazy load — call from property accessors."""
        with self._load_lock:
            if not self._loaded:
                self.load()

    @abstractmethod
    def load(self) -> None:
        """Load data from disk. Subclasses handle schema-specific parsing."""
        ...

    @abstractmethod
    def _get_save_data(self) -> dict[str, Any]:
        """Return the JSON-serializable dict to write to disk."""
        ...

    def save(self) -> None:
        """Save data to disk using atomic write pattern.

        Writes to a temporary file first, then atomically renames to target.
        This prevents data corruption from interrupted writes.

        Raises:
            OSError: If file cannot be written (subclass should wrap in
                     domain-specific error before propagation)
        """
        temp_path = self._file_path.with_suffix('.tmp')

        try:
            self._resources_path.mkdir(parents=True, exist_ok=True)

            data = self._get_save_data()

            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            temp_path.replace(self._file_path)

        except (OSError, TypeError) as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass  # Best effort cleanup
            raise OSError(f"Failed to save {self._file_path.name}: {e}") from e

    def reload(self) -> None:
        """Force reload data from disk.

        Use this when the file may have been modified externally.
        """
        self._loaded = False
        self.load()

    def _generate_id(self) -> str:
        """Generate a unique 8-character ID."""
        return str(uuid.uuid4())[:8]
