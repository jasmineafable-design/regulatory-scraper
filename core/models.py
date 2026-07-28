from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class ContentQuality(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNVERIFIED = "UNVERIFIED"


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


class CandidateIssuance(BaseModel):
    source_regulator: str
    source_category: str
    issuance_identifier: str
    issuance_title: str
    source_url: str
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    validation_status: str = "genuine"


class NormalizedIssuance(BaseModel):
    source_regulator: str
    source_category: str
    issuance_identifier: str
    issuance_title: str
    source_url: str
    raw_payload: Dict[str, Any] = Field(default_factory=dict)


class IssuanceStateRecord(BaseModel):
    issuance_identifier: str
    source_regulator: str
    first_seen_timestamp: Optional[str] = None
    last_processed_timestamp: Optional[str] = None
    status: str = "PROCESSED"
    raw_payload: Dict[str, Any] = Field(default_factory=dict)


class BriefingRecord(BaseModel):
    issuance_identifier: str
    source_regulator: str
    title: str
    summary: str
    quality: ContentQuality = ContentQuality.UNVERIFIED
    dispatch_timestamp: Optional[str] = None
