import json
import os
import logging
from typing import Set

logger = logging.getLogger(__name__)

class StateStore:
    """
    Manages historical state to identify new vs. previously processed issuances.
    """

    def __init__(self, state_file_path: str = "data/processed_state.json"):
        self.state_file_path = state_file_path
        self._ensure_directory()
        self.processed_ids: Set[str] = self._load_state()

    def _ensure_directory(self):
        os.makedirs(os.path.dirname(self.state_file_path), exist_ok=True)

    def _load_state(self) -> Set[str]:
        if not os.path.exists(self.state_file_path):
            return set()
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("processed_ids", []))
        except Exception as e:
            logger.error(f"Error loading state store: {str(e)}")
            return set()

    def is_processed(self, item_id: str) -> bool:
        return item_id in self.processed_ids

    def commit(self, item_id: str) -> None:
        """
        Adds a new issuance ID to state and persists to disk.
        """
        self.processed_ids.add(item_id)
        try:
            with open(self.state_file_path, "w", encoding="utf-8") as f:
                json.dump({"processed_ids": list(self.processed_ids)}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to commit state for {item_id}: {str(e)}")
            raise e
