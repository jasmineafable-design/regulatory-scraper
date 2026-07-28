import pytest
from core.adapters.base_adapter import BaseAdapter
from core.models import RawIssuance, CandidateIssuance, ContentQuality


class DummyAdapter(BaseAdapter):
    @property
    def regulator_id(self) -> str:
        return "DUMMY"

    def fetch_latest_issuances(self):
        return []


def test_base_adapter_abstract():
    adapter = DummyAdapter()
    assert adapter.regulator_id == "DUMMY"


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
    assert normalized.issuance_identifier is not None
    assert len(normalized.issuance_identifier) > 0


def test_quality_assessment():
    adapter = DummyAdapter()
    
    raw_valid = RawIssuance(
        regulator_id="TEST",
        category_id="CAT1",
        title="Valid Document Title",
        canonical_url="https://example.com/doc2",
        extracted_text="This is valid text content extracted from document."
    )
    normalized_valid = adapter.normalize(raw_valid)
    assert normalized_valid.content_quality in [ContentQuality.HIGH, ContentQuality.VALID]

    raw_empty = RawIssuance(
        regulator_id="TEST",
        category_id="CAT1",
        title="Empty Doc",
        canonical_url="https://example.com/doc3",
        extracted_text=""
    )
    normalized_empty = adapter.normalize(raw_empty)
    assert normalized_empty.content_quality in [ContentQuality.LOW, ContentQuality.UNVERIFIED]
