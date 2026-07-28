from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CandidateIssuance:
    """Normalized candidate issuance produced by adapters (§5.1)."""

    source_regulator: str  # BIR / IC / SEC
    source_category: str  # e.g., IC-CL, BIR-RMC, SEC-MC
    issuance_identifier: str  # Stable identifier in regulator's convention
    issuance_title: str
    source_url: str  # Official regulator link
    raw_content_reference: str  # Pointer/text to fetched raw content
    publication_date: Optional[str] = None
    fetched_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
    validation_status: str = "genuine"  # genuine / blocked / error / malformed


@dataclass
class BriefingRecord:
    """Composed briefing record for notification and state commitment (§5.2)."""

    issuance_identifier: str
    source_regulator: str
    source_category: str
    issuance_title: str
    official_source_link: str
    executive_summary: str = "UNAVAILABLE"
    insurance_entity_impact: str = "UNAVAILABLE"
    brokerage_entity_impact: str = "UNAVAILABLE"
    risk_priority_level: str = "UNAVAILABLE"
    suggested_action: str = "UNAVAILABLE"
    archived_document_link: str = "UNAVAILABLE"
    completeness_status: str = "degraded"  # complete / degraded
    composed_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
    notified_at: Optional[str] = None
    committed_at: Optional[str] = None
