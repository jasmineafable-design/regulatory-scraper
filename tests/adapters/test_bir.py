import pytest
from pathlib import Path
from src.adapters.bir import BIRAdapter


@pytest.fixture
def bir_sample_html():
    fixture_path = Path(__file__).parent / "fixtures" / "bir_sample.html"
    return fixture_path.read_text(encoding="utf-8")


def test_bir_adapter_validate_success(bir_sample_html):
    adapter = BIRAdapter()
    assert adapter.validate(bir_sample_html) is True


def test_bir_adapter_validate_failure_empty():
    adapter = BIRAdapter()
    assert adapter.validate("") is False


def test_bir_adapter_validate_failure_invalid_dom():
    adapter = BIRAdapter()
    assert adapter.validate("<html><body><div>No table here</div></body></html>") is False


def test_bir_adapter_parse(bir_sample_html):
    adapter = BIRAdapter()
    candidates = adapter.parse(bir_sample_html)

    assert len(candidates) == 2

    first = candidates[0]
    assert first["regulator"] == "BIR"
    assert first["issuance_number"] == "RMC No. 12-2026"
    assert first["title"] == "Clarifying Tax Rules on Digital Transactions"
    assert first["issue_date"] == "February 10, 2026"
    assert first["source_url"] == "https://www.bir.gov.ph/images/bir_files/internal_revenue_issuances/rmc12-2026.pdf"
    assert first["category"] == "RMC"

    second = candidates[1]
    assert second["issuance_number"] == "RMC No. 11-2026"
