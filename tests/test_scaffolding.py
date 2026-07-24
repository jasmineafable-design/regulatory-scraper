import pytest
from core.config import SystemConfig
from core.logger import setup_logger
from core.base_adapter import BaseSourceAdapter
from core.models import RawIssuance, ContentQuality


class DummyAdapter(BaseSourceAdapter):
    """Temporary adapter created solely to test base adapter behavior."""
    @property
    def regulator_id(self) -> str:
        return "TEST_REGULATOR"

    def fetch_latest_issuances(self, category_id: str, config: dict):
        return []


def test_logger_creation():
    logger = setup_logger("test_component")
    assert logger.name == "test_component"


def test_config_defaults():
    config = SystemConfig.load()
    assert config.environment in ["development", "production", "test"]


def test_deterministic_identifier_fallback():
    adapter = DummyAdapter()
    
    # Raw issuance missing an official document number
    raw = RawIssuance(
        regulator_id="TEST",
        category_id="CAT1",
        title="Sample Circular Title",
        canonical_url="https://example.com/doc1",
        raw_identifier=None
    )
    
    normalized = adapter.normalize(raw)
    
    # Verify fallback ID is non-null and correctly prefixed
    assert normalized.issuance_id.startswith("TEST_HASH_")
    assert len(normalized.issuance_id) > 10


def test_quality_assessment_unextractable():
    adapter = DummyAdapter()
    raw = RawIssuance(
        regulator_id="TEST",
        category_id="CAT1",
        title="Empty Doc",
        canonical_url="https://example.com/doc2",
        extracted_text=""
    )
    normalized = adapter.normalize(raw)
    assert normalized.content_quality == ContentQuality.UNEXTRACTABLE_PDF
