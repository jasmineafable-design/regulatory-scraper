from datetime import datetime, timezone
from typing import Optional
from core.models import CandidateIssuance, BriefingRecord


def compose_briefing(
    candidate: CandidateIssuance,
    executive_summary: Optional[str] = None,
    insurance_entity_impact: Optional[str] = None,
    brokerage_entity_impact: Optional[str] = None,
    risk_priority_level: Optional[str] = None,
    suggested_action: Optional[str] = None,
    archived_document_link: Optional[str] = None,
) -> BriefingRecord:
    """
    Assembles a BriefingRecord from a CandidateIssuance (Section 5.2).
    
    Deterministic fields are always populated. AI-advisory and archive fields 
    are populated if available, or explicitly left as None (unavailable) per Section 3.4.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    # Determine completeness status (Section 5.2 & Approved Fail-Open Decision Section 3.4)
    # In Phase 1, AI fields are stubbed, so briefing defaults to 'degraded' 
    # until AI Assess (Phase 4) is wired in.
    has_ai_analysis = executive_summary is not None
    completeness_status = "complete" if has_ai_analysis else "degraded"

    return BriefingRecord(
        issuance_identifier=candidate.issuance_identifier,
        source_regulator=candidate.source_regulator,
        source_category=candidate.source_category,
        issuance_title=candidate.issuance_title,
        official_source_link=candidate.source_url,
        completeness_status=completeness_status,
        composed_at=now_iso,
        executive_summary=executive_summary,
        insurance_entity_impact=insurance_entity_impact,
        brokerage_entity_impact=brokerage_entity_impact,
        risk_priority_level=risk_priority_level,
        suggested_action=suggested_action,
        archived_document_link=archived_document_link,
        notified_at=None,
        committed_at=None,
    )
