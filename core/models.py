from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ContentQuality(Enum):
    """Quality classification for scraped document text."""
    VALID = "VALID"
    LOW_QUALITY = "LOW_QUALITY"
    UNEXTRACTABLE_PDF = "UNEXTRACTABLE_PDF"


@dataclass(frozen=True)
class RawIssuance:
    """Represents a single raw regulatory publication scraped directly from a website."""
    regulator_id: str
    category_id: str
    title: str
    canonical_url: str
    raw_identifier: Optional[str] = None
    published_date_str: Optional[str] = None
    pdf_url: Optional[str] = None
    extracted_text: Optional[str] = None


@dataclass(frozen=True)
class NormalizedIssuance:
    """Represents a clean regulatory publication with a guaranteed unique identifier."""
    issuance_id: str
    regulator_id: str
    category_id: str
    title: str
    canonical_url: str
    content_quality: ContentQuality
    published_date_str: Optional[str] = None
    pdf_url: Optional[str] = None
    cleaned_text: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScraperTargetConfig:
    """Configuration settings for a single regulatory scraping category."""
    regulator_id: str
    category_id: str
    category_name: str
    enabled: bool
    check_interval_hours: int = 24


@dataclass(frozen=True)
class BusinessEntityConfig:
    """Business context guidance for AI risk evaluation."""
    entity_code: str
    entity_full_name: str
    primary_focus: str
    key_topics_of_interest: List[str]
