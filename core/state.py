import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Set
from core.logger import setup_logger
from core.models import IssuanceStateRecord, NormalizedIssuance

logger = setup_logger("state")

DEFAULT_STATE_FILE_PATH = Path(__file__).resolve().parent.parent / "data" / "state.json"


class StateManager:
    """Manages system memory, preventing duplicate alerts via atomic JSON storage."""

    def __init__(self, file_path: Path = DEFAULT_STATE_FILE_PATH):
        self.file_path = Path(file_path)
        self.records: Dict[str, dict] = {}
        self._ensure_directory_exists()
        self.load_state()

    def _ensure_directory_exists(self) -> None:
        """Creates the data directory if it does not exist."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> None:
        """Loads recorded state from JSON storage file."""
        if not self.file_path.exists():
            logger.info(f"No existing state file found at {self.file_path}. Initializing new state ledger.")
            self.records = {}
            self._save_state_atomic()
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                self.records = json.load(f)
            logger.info(f"State ledger loaded successfully. Total remembered items: {len(self.records)}")
        except Exception as e:
            logger.error(f"Failed to read state ledger at {self.file_path}: {e}. Initializing empty in-memory state.")
            self.records = {}

    def is_seen(self, issuance_id: str) -> bool:
        """Returns True if the given issuance_id has already been recorded in state."""
        return issuance_id in self.records

    def record_issuance(
        self,
        issuance: NormalizedIssuance,
        status: str = "PROCESSED"
    ) -> None:
        """Adds a normalized issuance to the in-memory state record."""
        now_iso = datetime.now(timezone.utc).isoformat()
        record = IssuanceStateRecord(
            issuance_id=issuance.issuance_id,
            regulator_id=issuance.regulator_id,
            category_id=issuance.category_id,
            first_seen_timestamp=now_iso,
            processed_status=status,
            title=issuance.title,
            canonical_url=issuance.canonical_url,
        )
        self.records[issuance.issuance_id] = {
            "issuance_id": record.issuance_id,
            "regulator_id": record.regulator_id,
            "category_id": record.category_id,
            "first_seen_timestamp": record.first_seen_timestamp,
            "processed_status": record.processed_status,
            "title": record.title,
            "canonical_url": record.canonical_url,
        }
        logger.info(f"State updated in-memory for issuance: {issuance.issuance_id} (Status: {status})")

    def seed_baseline(self, issuance: NormalizedIssuance) -> None:
        """Seeds historical issuances into state marked as BASELINE so they don't trigger alerts."""
        if not self.is_seen(issuance.issuance_id):
            self.record_issuance(issuance, status="BASELINE")

    def commit(self) -> bool:
        """Persists in-memory state updates atomically to disk."""
        return self._save_state_atomic()

    def _save_state_atomic(self) -> bool:
        """Writes state to a temporary file first, then swaps it atomically.
        
        This prevents file corruption if the process crashes mid-write.
        """
        temp_file = self.file_path.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.records, f, indent=2, ensure_ascii=False)

            # Atomic swap (replaces destination file safely)
            os.replace(temp_file, self.file_path)
            logger.info(f"State ledger successfully saved to {self.file_path}. ({len(self.records)} records)")
            return True
        except Exception as e:
            logger.error(f"Critical error writing state file atomically: {e}")
            if temp_file.exists():
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
            return False
