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

    def
