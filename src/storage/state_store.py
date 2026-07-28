import json
import os
import logging
from typing import Set

logger = logging.getLogger("StateStore")

class StateStore:
    def __init__(self, state_file_path: str = "data/processed_state.json", storage_filepath: str = None):
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

    # --- Methods expected by Orchestrator & Unit Tests ---
    def is_processed(self, item_id: str) -> bool:
        """Checks if a given item ID or URL has been processed."""
        return str(item_id).strip() in self.seen_ids

    def commit(self, item_id: str) -> None:
        """Marks an item ID as processed and persists to file."""
        self.seen_ids.add(str(item_id).strip())
        self._save_state()

    def add(self, item_id: str) -> None:
        """Alias for commit."""
        self.commit(item_id)

    # --- Methods for multi-parameter signature ---
    def is_seen(self, regulator: str, identifier: str) -> bool:
        composite_key = f"{regulator.strip().upper()}:{identifier.strip()}"
        return composite_key in self.seen_ids

    def mark_seen(self, regulator: str, identifier: str) -> None:
        composite_key = f"{regulator.strip().upper()}:{identifier.strip()}"
        self.seen_ids.add(composite_key)
        self._save_state()

# Class Alias
StateManager = StateStore
