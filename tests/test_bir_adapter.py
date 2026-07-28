import pytest
from core.adapters.bir_adapter import BIRAdapter
from core.models import RawIssuance, CandidateIssuance

SAMPLE_BIR_HTML = """
<table>
    <tr><th>Subject</th><th>Link</th></tr>
    <tr>
        <td>RMC No. 15-2026 Publishes the revised guidelines on VAT zero-rated sales for exporters.</td>
        <td><a href="/pdf/rmc15-2026.pdf">Download PDF</a></td>
    </tr>
    <tr>
        <td>RMC No. 16-2026 Clarification on tax treatment of digital services.</td>
        <td><a href="/pdf/rmc16-2026.pdf">Download PDF</a></td>
    </tr>
</table>
"""


def test_bir_adapter_instantiation():
    adapter = BIRAdapter()
    assert adapter.regulator_id == "BIR"


def test_bir_adapter_identifier_extraction():
    adapter = BIRAdapter()
    extracted = adapter._extract_identifier("RMC No. 15-2026 Guidelines on VAT", "RMC")
    assert extracted == "RMC No. 15-2026"


def test_bir_adapter_parse_html_page():
    adapter = BIRAdapter()
    base_url = "https://www.bir.gov.ph/revenue-issuances-details"

    raw_issuances = adapter.parse_html_page(SAMPLE_BIR_HTML, base_url, "RMC")
    assert len(raw_issuances) == 2
    assert raw_issuances[0].source_regulator == "BIR"


def test_bir_adapter_normalization():
    adapter = BIRAdapter()
    base_url = "https://www.bir.gov.ph/revenue-issuances-details"

    raw_list = adapter.parse_html_page(SAMPLE_BIR_HTML, base_url, "RMC")
    normalized = adapter.normalize(raw_list[0])

    # Clean identifier without artificial regulator prefixing
    assert normalized.issuance_identifier == "RMC No. 15-2026"
    assert normalized.source_regulator == "BIR"


def test_bir_adapter_fetch_latest_issuances():
    adapter = BIRAdapter()
    candidates = adapter.fetch_latest_issuances()

    assert len(candidates) > 0
    candidate = candidates[0]
    assert isinstance(candidate, CandidateIssuance)
    assert candidate.source_regulator == "BIR"
    assert candidate.issuance_identifier == "RMC No. 15-2026"
