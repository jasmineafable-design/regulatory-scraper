from datetime import datetime
import logging
from typing import List
from models.issuance import BriefingRecord
from core.state import StateManager

logger = logging.getLogger(__name__)


class StateCommitter:
    """Applies §3.6 state commit rule: mark processed only after Notify succeeds."""

    def __init__(self, state_manager: StateManager):
        self.state_manager = state_manager

    def commit_notified_briefings(
        self, notified_briefings: List[BriefingRecord]
    ) -> None:
        """Commits each successfully notified briefing record into persistent state."""
        now_iso = datetime.utcnow().isoformat()
        for briefing in notified_briefings:
            briefing.committed_at = now_iso
            self.state_manager.mark_seen(
                item_id=briefing.issuance_identifier,
                agency=briefing.source_regulator,
                title=briefing.issuance_title,
                status="PROCESSED",
            )
            logger.info(
                f"Committed issuance {briefing.issuance_identifier} to state."
            )
