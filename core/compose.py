from models.issuance import BriefingRecord, CandidateIssuance


class Composer:
    """Assembles the content-contract Briefing Record (§3.2, §5.2)."""

    def compose_briefing(self, candidate: CandidateIssuance) -> BriefingRecord:
        """Transforms a CandidateIssuance into a BriefingRecord.
        
        In Phase 1, AI and best-effort fields are stubbed as UNAVAILABLE,
        and completeness_status is set to 'degraded'.
        """
        return BriefingRecord(
            issuance_identifier=candidate.issuance_identifier,
            source_regulator=candidate.source_regulator,
            source_category=candidate.source_category,
            issuance_title=candidate.issuance_title,
            official_source_link=candidate.source_url,
            executive_summary="UNAVAILABLE",
            insurance_entity_impact="UNAVAILABLE",
            brokerage_entity_impact="UNAVAILABLE",
            risk_priority_level="UNAVAILABLE",
            suggested_action="UNAVAILABLE",
            archived_document_link="UNAVAILABLE",
            completeness_status="degraded",
        )
