from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class ContentQuality(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNVERIFIED = "UNVERIFIED"
    VALID = "VALID"


class BusinessEntityConfig(BaseModel):
    entity_code: Optional[str] = None
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    name: Optional[str] = None
    monitored_regulators: List[str] = Field(default_factory=list)
    monitored_categories: List[str] = Field(default_factory=list)


class ScraperTargetConfig(BaseModel):
    regulator_id: str
    enabled: bool = True
    base_url: Optional[str] = None
    adapter_class: Optional[str] = None
    check_interval_hours: int = 24


class RawIssuance(BaseModel):
    source_regulator: Optional[str] = Field(default="UNKNOWN", alias="regulator_id")
    regulator_id: Optional[str] = None
    category_id: Optional[str] = None
    title: Optional[str] = None
    canonical_url: Optional[str] = None
    raw_identifier: Optional[str] = None
    published_date_str: Optional[str] = None
    extracted_text: Optional[str] = None
    raw_content: Dict[str, Any] = Field(default_factory=dict)
    fetched_at: Optional[str] = None

    def __init__(self, **data: Any):
        if "regulator_id" in data and "source_regulator" not in data:
            data["source_regulator"] = data["regulator_id"]
        super().__init__(**data)


class CandidateIssuance(BaseModel):
    source_regulator: str
    source_category: str
    issuance_identifier: str
    issuance_title: str
    source_url: str
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    validation_status: str = "genuine"


class NormalizedIssuance(BaseModel):
    source_regulator: Optional[str] = Field(default="UNKNOWN", alias="regulator_id")
    regulator_id: Optional[str] = None
    category_id: Optional[str] = None
    issuance_id: Optional[str] = None
    issuance_identifier: Optional[str] = None
    issuance_title: Optional[str] = None
    title: Optional[str] = None
    source_url: Optional[str] = None
    canonical_url: Optional[str] = None
    content_quality: Optional[ContentQuality] = ContentQuality.UNVERIFIED
    raw_payload: Dict[str, Any] = Field(default_factory=dict)

    def __init__(self, **data: Any):
        if "regulator_id" in data and "source_regulator" not in data:
            data["source_regulator"] = data["regulator_id"]
        if "issuance_id" in data and "issuance_identifier" not in data:
            data["issuance_identifier"] = data["issuance_id"]
        if "title" in data and "issuance_title" not in data:
            data["issuance_title"] = data["title"]
        if "canonical_url" in data and "source_url" not in data:
            data["source_url"] = data["canonical_url"]
        super().__init__(**data)


class IssuanceStateRecord(BaseModel):
    issuance_identifier: Optional[str] = Field(default=None, alias="issuance_id")
    source_regulator: Optional[str] = Field(default="UNKNOWN", alias="regulator_id")
    issuance_id: Optional[str] = None
    regulator_id: Optional[str] = None
    category_id: Optional[str] = None
    title: Optional[str] = None
    canonical_url: Optional[str] = None
    processed_status: Optional[str] = None
    first_seen_timestamp: Optional[str] = None
    last_processed_timestamp: Optional[str] = None
    status: str = "PROCESSED"
    raw_payload: Dict[str, Any] = Field(default_factory=dict)

    def __init__(self, **data: Any):
        if "issuance_id" in data and "issuance_identifier" not in data:
            data["issuance_identifier"] = data["issuance_id"]
        if "regulator_id" in data and "source_regulator" not in data:
            data["source_regulator"] = data["regulator_id"]
        super().__init__(**data)


class BriefingRecord(BaseModel):
    issuance_identifier: str
    source_regulator: str
    title: str
    summary: str
    quality: ContentQuality = ContentQuality.UNVERIFIED
    dispatch_timestamp: Optional[str] = None
