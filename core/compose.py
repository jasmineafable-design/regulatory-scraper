import logging
from typing import Optional

from models.issuance import BriefingRecord, CandidateIssuance

logger = logging.getLogger(__name__)


class Composer:
    """Assembles the content-contract Briefing Record (§3.2, §5.2).

    Assess (Phase 4) and Archive (Phase 5) are both AI-advisory/best-effort
    (§3.8, Foundation principle 10): each is optional to supply, and each is
    independently allowed to fail without affecting the other or blocking
    the briefing. completeness_status is "complete" only if every supplied
    best-effort step succeeded; it is "degraded" if any of them was either
    not supplied or failed -- the briefing still goes out immediately with
    all available deterministic information; it is never withheld or
    silently incomplete.
    """

    def __init__(self, assessor: Optional[object] = None, archiver: Optional[object] = None):
        self.assessor = assessor
        self.archiver = archiver

    def compose_briefing(self, candidate: CandidateIssuance) -> BriefingRecord:
        executive_summary = "UNAVAILABLE"
        insurance_entity_impact = "UNAVAILABLE"
        brokerage_entity_impact = "UNAVAILABLE"
        risk_priority_level = "UNAVAILABLE"
        suggested_action = "UNAVAILABLE"
        archived_document_link = "UNAVAILABLE"
        attachment_filename = None
        attachment_content_type = None
        attachment_bytes = None

        # Tracks which *supplied* best-effort steps actually succeeded --
        # tracked as explicit flags rather than inferred from field values,
        # since a successful Assess call can still legitimately produce the
        # literal string "UNAVAILABLE" for a field with nothing to report.
        supplied_results = []

        if self.assessor is not None:
            result = self.assessor.assess(candidate)
            supplied_results.append(result.succeeded)
            if result.succeeded:
                executive_summary = result.executive_summary
                insurance_entity_impact = result.insurance_entity_impact
                brokerage_entity_impact = result.brokerage_entity_impact
                risk_priority_level = result.risk_priority_level
                suggested_action = result.suggested_action
            else:
                logger.warning(
                    f"[{candidate.source_regulator}] AI assessment unavailable for "
                    f"{candidate.issuance_identifier} ({result.error}) -- briefing "
                    "will go out with AI fields marked UNAVAILABLE, per the frozen "
                    "fail-open behavior."
                )

        if self.archiver is not None:
            archive_result = self.archiver.archive(candidate)
            supplied_results.append(archive_result.succeeded)
            if archive_result.succeeded:
                archived_document_link = archive_result.archived_document_link
                attachment_filename = archive_result.attachment_filename
                attachment_content_type = archive_result.attachment_content_type
                attachment_bytes = archive_result.attachment_bytes
            else:
                logger.warning(
                    f"[{candidate.source_regulator}] Document archiving unavailable for "
                    f"{candidate.issuance_identifier} ({archive_result.error}) -- briefing "
                    "will go out with the archive link marked UNAVAILABLE, per the frozen "
                    "fail-open behavior."
                )

        # "complete" requires every *supplied* best-effort step to have
        # succeeded -- Assess succeeding says nothing about Archive, and
        # vice versa (§3.8: either one failing, or neither being supplied at
        # all, means the briefing is explicitly degraded, never silently
        # presented as complete).
        completeness_status = "complete" if supplied_results and all(supplied_results) else "degraded"

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
            archived_document_link=archived_document_link,
            attachment_filename=attachment_filename,
            attachment_content_type=attachment_content_type,
            attachment_bytes=attachment_bytes,
            completeness_status=completeness_status,
        )
