import logging
from typing import List, Tuple
from models.issuance import CandidateIssuance
from core.state import StateManager

logger = logging.getLogger(__name__)


class Detector:
    """Handles deterministic deduplication and baseline state handling (§3.6)."""

    def __init__(self, state_manager: StateManager):
        self.state_manager = state_manager

    def detect_new_issuances(
        self,
        candidates: List[CandidateIssuance],
        is_category_baseline: bool = False,
    ) -> List[CandidateIssuance]:
        """Compares validated candidates against known state.
        
        If `is_category_baseline` is True, records candidates directly into state
        without marking them as new (§13 baseline exclusion).
        """
        new_candidates: List[CandidateIssuance] = []

        for candidate in candidates:
            if candidate.validation_status != "genuine":
                logger.warning(
                    f"Skipping candidate {candidate.issuance_identifier} due to "
                    f"validation status: {candidate.validation_status}"
                )
                continue

            item_id = candidate.issuance_identifier

            if self.state_manager.is_seen(item_id):
                logger.debug(f"Issuance {item_id} already exists in state.")
                continue

            if is_category_baseline:
                logger.info(
                    f"Baselining category item {item_id} into state without notifying."
                )
                self.state_manager.mark_seen(
                    item_id=item_id,
                    agency=candidate.source_regulator,
                    title=candidate.issuance_title,
                    status="BASELINE",
                )
            else:
                new_candidates.append(candidate)

        return new_candidates
