import logging
from typing import Optional

from models.issuance import BriefingRecord, CandidateIssuance

logger = logging.getLogger(__name__)


class Composer:
    """Assembles the content-contract Briefing Record (§3.2, §5.2).

    Assess (Phase 4) is AI-advisory and best-effort (§3.8, Foundation
    principle 10): if an Assessor is supplied and succeeds, its fields are
    used and completeness_status is "complete". If no Assessor is supplied,
    or it fails for any reason, every AI-derived field stays "UNAVAILABLE"
    and completeness_status is "degraded" -- the briefing still goes out
    immediately with all available deterministic information; it is never
    withheld or silently incomplete.
    """

    def __init__(self, assessor: Optional[object] = None):
        self.assessor = assessor

    def compose_briefing(self, candidate: CandidateIssuance) -> BriefingRecord:
        executive_summary = "UNAVAILABLE"
        insurance_entity_impact = "UNAVAILABLE"
        brokerage_entity_impact = "UNAVAILABLE"
        risk_priority_level = "UNAVAILABLE"
        suggested_action = "UNAVAILABLE"
        completeness_status = "degraded"

        if self.assessor is not None:
            result = self.assessor.assess(candidate)
            if result.succeeded:
                executive_summary = result.executive_summary
                insurance_entity_impact = result.insurance_entity_impact
                brokerage_entity_impact = result.brokerage_entity_impact
                risk_priority_level = result.risk_priority_level
                suggested_action = result.suggested_action
                completeness_status = "complete"
            else:
                logger.warning(
                    f"[{candidate.source_regulator}] AI assessment unavailable for "
                    f"{candidate.issuance_identifier} ({result.error}) -- briefing "
                    "will go out with AI fields marked UNAVAILABLE, per the frozen "
                    "fail-open behavior."
                )

        return BriefingRecord(
            issuance_identifier=candidate.issuance_identifier,
            source_regulator=candidate.source_regulator,
            source_category=candidate.source_category,
            issuance_title=candidate.issuance_title,
            official_source_link=candidate.source_url,
            executive_summary=executive_summary,
            insurance_entity_impact=insurance_entity_impact,
            brokerage_entity_impact=brokerage_entity_impact,
            risk_priority_level=risk_priority_level,
            suggested_action=suggested_action,
            archived_document_link="UNAVAILABLE",
            completeness_status=completeness_status,
        )
