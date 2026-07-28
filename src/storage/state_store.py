# Location: src/storage/state_store.py

import json
import os
import logging
from typing import Set

logger = logging.getLogger("StateStore")

class StateStore:
    def __init__(self, state_file_path: str = "data/processed_state.json", storage_filepath: str = None):
        # Support both state_file_path and storage_filepath keyword arguments
        self.storage_filepath = storage_filepath or state_file_path
        self.seen_ids: Set[str] = self._load_state()

    def _load_state(self) -> Set[str]:
        if not os.path.exists(self.storage_filepath):
            return set()
        try:
            with open(self.storage_filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("seen_ids", []))
        except Exception as e:
            logger.error(f"Error loading state file: {e}")
            return set()

    def _save_state(self) -> None:
        os.makedirs(os.path.dirname(self.storage_filepath), exist_ok=True)
        try:
            with open(self.storage_filepath, "w", encoding="utf-8") as f:
                json.dump({"seen_ids": list(self.seen_ids)}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving state file: {e}")

    def is_seen(self, regulator: str, identifier: str) -> bool:
        """Checks if a regulator-issuance pair has already been processed."""
        composite_key = f"{regulator.strip().upper()}:{identifier.strip()}"
        return composite_key in self.seen_ids

    def mark_seen(self, regulator: str, identifier: str) -> None:
        """Marks an issuance as seen and persists to local JSON state."""
        composite_key = f"{regulator.strip().upper()}:{identifier.strip()}"
        self.seen_ids.add(composite_key)
        self._save_state()

# Backward compatibility alias
StateManager = StateStore
