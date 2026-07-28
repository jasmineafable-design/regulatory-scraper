import json
import os
from typing import Set

from core.logger import setup_logger

logger = setup_logger("state")


class StateManager:
    """Manages persistence of seen issuance identifiers to avoid duplicate alerts."""

    def __init__(self, filepath: str = "state/seen_issuances.json"):
        self.filepath = filepath
        self.seen_identifiers: Set[str] = set()
        self.load_state()

    def _make_key(self, regulator: str, identifier: str) -> str:
        """Constructs a composite state key."""
        return f"{regulator.upper()}::{identifier.strip()}"

    def is_seen(self, regulator: str, identifier: str) -> bool:
        """Checks if an issuance has already been processed."""
        key = self._make_key(regulator, identifier)
        return key in self.seen_identifiers

    def mark_seen(self, regulator: str, identifier: str) -> None:
        """Marks an issuance as processed in memory."""
        key = self._make_key(regulator, identifier)
        self.seen_identifiers.add(key)

    def load_state(self) -> None:
        """Loads state from JSON file on disk if it exists."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.seen_identifiers = set(data)
                    logger.info(f"Loaded {len(self.seen_identifiers)} seen item(s) from {self.filepath}")
            except Exception as e:
                logger.error(f"Failed to load state file {self.filepath}: {e}", exc_info=True)
                self.seen_identifiers = set()
        else:
            logger.info(f"No existing state file found at {self.filepath}. Starting fresh.")
            self.seen_identifiers = set()

    def save_state(self) -> None:
        """Saves current seen identifiers set to disk as JSON."""
        try:
            dir_name = os.path.dirname(self.filepath)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(sorted(list(self.seen_identifiers)), f, indent=2)
            logger.info(f"Saved {len(self.seen_identifiers)} item(s) to state file {self.filepath}")
        except Exception as e:
            logger.error(f"Failed to save state file {self.filepath}: {e}", exc_info=True)
