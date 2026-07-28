from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class ContentQuality(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNVERIFIED = "UNVERIFIED"


class BusinessEntityConfig(BaseModel):
    entity_id: str
    entity_name: str
    monitored_regulators: List[str] = Field(default_factory=list)


class ScraperTargetConfig(BaseModel):
    regulator_id: str
    enabled: bool = True
    base_url: str
    adapter_class: str


class CandidateIssuance(BaseModel):
    source_regulator: str
    source_category: str
    issuance_identifier: str
    issuance_title: str
    source_url: str
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    validation_status: str = "genuine"


class BriefingRecord(BaseModel):
    issuance_identifier: str
    source_regulator: str
    title: str
    summary: str
    quality: ContentQuality = ContentQuality.UNVERIFIED
    dispatch_timestamp: Optional[str] = None
