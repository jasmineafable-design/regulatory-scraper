from dataclasses import dataclass
from typing import Optional


@dataclass
class CandidateIssuance:
    """Standardized output emitted by regulator source adapters (Section 5.1)."""

    source_regulator: str  # Regulator name: 'BIR', 'IC', 'SEC'
    source_category: str  # Issuance category (e.g., 'RMC', 'CL', 'MC')
    issuance_identifier: str  # Stable ID in regulator's convention (used for dedup)
    issuance_title: str  # Human-readable title
    source_url: str  # Official regulator link
    raw_content_reference: str  # Pointer/text reference to raw content for Assess/Archive
    fetched_at: str  # ISO timestamp of fetch attempt
    validation_status: str  # Status: 'genuine', 'blocked', 'error', 'malformed'
    publication_date: Optional[str] = None  # Date published, if available


@dataclass
class BriefingRecord:
    """Assembled content-contract briefing payload (Section 5.2)."""

    # Carried from Candidate Issuance
    issuance_identifier: str
    source_regulator: str
    source_category: str
    issuance_title: str

    # Official link
    official_source_link: str

    # Pipeline status
    completeness_status: str  # 'complete' or 'degraded'
    composed_at: str  # ISO timestamp when composed

    # AI-Advisory fields (explicitly marked/set as unavailable if failed or missing)
    executive_summary: Optional[str] = None
    insurance_entity_impact: Optional[str] = None  # Impact on MIGI / MILI
    brokerage_entity_impact: Optional[str] = None  # Impact on MIBI
    risk_priority_level: Optional[str] = None
    suggested_action: Optional[str] = None

    # Best-effort document link
    archived_document_link: Optional[str] = None

    # Lifecycle commitment timestamps
    notified_at: Optional[str] = None
    committed_at: Optional[str] = None
