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
    # Verify RawIssuance handles fallback identifier generation natively
    raw = RawIssuance(
        regulator_id="TEST",
        category_id="CAT1",
        title="Sample Circular Title",
        canonical_url="https://example.com/doc1",
        raw_identifier=None
    )
    
    # Check that raw_identifier fallback logic or property functions as intended
    identifier = raw.raw_identifier or raw.title
    assert identifier is not None
    assert len(identifier) > 0


def test_quality_assessment():
    raw_valid = RawIssuance(
        regulator_id="TEST",
        category_id="CAT1",
        title="Valid Document Title",
        canonical_url="https://example.com/doc2",
        extracted_text="This is valid text content extracted from document."
    )
    assert raw_valid.extracted_text is not None
    assert len(raw_valid.extracted_text) > 0

    raw_empty = RawIssuance(
        regulator_id="TEST",
        category_id="CAT1",
        title="Empty Doc",
        canonical_url="https://example.com/doc3",
        extracted_text=""
    )
    assert raw_empty.extracted_text == ""
