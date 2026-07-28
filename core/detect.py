from typing import List
from core.models import CandidateIssuance
from state.manager import is_issuance_known


def detect_new_issuances(candidates: List[CandidateIssuance]) -> List[CandidateIssuance]:
    """
    Compares candidate issuances against known state records and filters out duplicates (Section 3.6).
    
    Returns:
        List[CandidateIssuance]: A list containing only new, uncommitted issuances.
    """
    new_candidates: List[CandidateIssuance] = []

    for candidate in candidates:
        # Ignore items that failed validation before detection
        if candidate.validation_status != "genuine":
            continue

        # Check if this item is already recorded in Issuance State
        already_processed = is_issuance_known(
            regulator=candidate.source_regulator,
            identifier=candidate.issuance_identifier
        )

        if not already_processed:
            new_candidates.append(candidate)

    return new_candidates
