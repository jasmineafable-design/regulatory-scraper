import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import settings

logger = logging.getLogger(__name__)


class StateManager:
    """Manages persistence of seen issuances across scraper runs."""

    def __init__(self, filepath: Optional[str] = None, state_file: Optional[str] = None):
        # Support both 'filepath' and 'state_file' keyword arguments
        resolved_path = filepath or state_file or settings.STATE_FILE_PATH
        self.filepath = Path(resolved_path)
        self.seen_data: Dict[str, Dict[str, Any]] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Loads state data from the JSON file if it exists."""
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    # A leftover/legacy state file (e.g. a list-shaped format
                    # from an older, incompatible implementation) isn't a
                    # crash-worthy error -- treat it as "no prior state" and
                    # start fresh. Re-detecting already-known issuances as new
                    # produces at most a duplicate notification, which the
                    # architecture explicitly accepts (§3.4 principle 7);
                    # crashing the whole run instead would be worse.
                    logger.error(
                        f"State file at {self.filepath} was not in the expected "
                        f"format (got {type(loaded).__name__}, expected an object) "
                        f"-- ignoring it and starting with fresh state."
                    )
                    self.seen_data = {}
                else:
                    self.seen_data = loaded
            except Exception as e:
                logger.error(f"Failed to load state file at {self.filepath}: {e}")
                self.seen_data = {}
        else:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            self.seen_data = {}
            self._save_state()

    def _save_state(self) -> None:
        """Saves current state data to the JSON file."""
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.seen_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state file at {self.filepath}: {e}")

    def is_seen(self, item_id: str) -> bool:
        """Checks if an item ID has already been recorded."""
        return item_id in self.seen_data

    def mark_seen(
        self,
        item_id: str,
        agency: str,
        title: str,
        status: str = "PROCESSED",
        category: Optional[str] = None,
    ) -> None:
        """Records an item as seen and persists state to disk."""
        self.seen_data[item_id] = {
            "agency": agency,
            "category": category,
            "title": title,
            "status": status,
        }
        self._save_state()

    def is_category_baselined(self, agency: str, category: str) -> bool:
        """Returns True if any record for this agency/category has ever been stored.

        Used to implement the §13 baseline-exclusion rule: a category's first-ever
        run must record its backlog as known without notifying on it.
        """
        return any(
            record.get("agency") == agency and record.get("category") == category
            for record in self.seen_data.values()
        )

    # -- Run-tracking (core/schedule.py) --------------------------------------
    # Stored under a reserved "__meta__" key in the same JSON file rather than a
    # separate store, so schedule-decision state travels with the rest of
    # Issuance State (§3.5) instead of introducing a fifth record. "__meta__" is
    # not a valid issuance identifier, so it can't collide with real entries.

    def get_last_run_at(self) -> Optional[str]:
        """ISO timestamp of the last completed run, or None if there's no history."""
        return self.seen_data.get("__meta__", {}).get("last_run_at")

    def get_last_opening_check_date(self) -> Optional[str]:
        """ISO date (YYYY-MM-DD) of the last run recognized as an opening check."""
        return self.seen_data.get("__meta__", {}).get("last_opening_check_date")

    def record_run(self, run_at: str, is_opening_check: bool) -> None:
        """Records that a run happened, for core.schedule's next decision."""
        meta = self.seen_data.setdefault("__meta__", {})
        meta["last_run_at"] = run_at
        if is_opening_check:
            meta["last_opening_check_date"] = run_at[:10]
        self._save_state()
