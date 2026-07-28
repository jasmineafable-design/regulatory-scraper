import pytest
from core.adapters.ic_adapter import ICAdapter
from core.models import CandidateIssuance

SAMPLE_IC_CL_HTML = """
<table>
    <tr>
        <td>CL No. 2026-05 Guidelines on Capital Requirements</td>
        <td><a href="/cl-2026-05.pdf">PDF</a></td>
    </tr>
</table>
"""

SAMPLE_IC_MULTI_HTML = """
<table>
    <tr>
        <td>Advisory No. 2026-02 Public Warning on Unregistered Entities</td>
        <td><a href="/adv-2026-02.pdf">PDF</a></td>
    </tr>
    <tr>
        <td>MC No. 2026-01 Memorandum on Compliance Reports</td>
        <td><a href="/mc-2026-01.pdf">PDF</a></td>
    </tr>
</table>
"""


def test_ic_adapter_instantiation():
    adapter = ICAdapter()
    assert adapter.regulator_id == "IC"


def test_ic_adapter_identifier_extraction_all_types():
    adapter = ICAdapter()

    # Verify standard identifier canonicalization
    assert adapter._extract_identifier("CL No. 2026-05 Guidelines", "CL") == "CL No. 2026-05"
    assert adapter._extract_identifier("Circular Letter No. 2026-01 Rules", "CL") == "CL No. 2026-01"


def test_ic_adapter_parse_advisory_and_mc_page():
    adapter = ICAdapter()
    base_url = "https://www.insurance.gov.ph/category/advisories/"

    raw_issuances = adapter.parse_html_page(SAMPLE_IC_MULTI_HTML, base_url, "ADV")
    assert len(raw_issuances) == 2

    adv_item = raw_issuances[0]
    assert adv_item.raw_identifier == "ADV No. 2026-02"


def test_ic_adapter_normalization():
    adapter = ICAdapter()
    base_url = "https://www.insurance.gov.ph/category/circular-letters/"

    raw_list = adapter.parse_html_page(SAMPLE_IC_CL_HTML, base_url, "CL")
    normalized = adapter.normalize(raw_list[0])

    assert normalized.issuance_identifier == "CL No. 2026-05"
    assert normalized.source_regulator == "IC"


def test_ic_adapter_fetch_latest_issuances():
    adapter = ICAdapter()
    candidates = adapter.fetch_latest_issuances()

    assert len(candidates) > 0
    candidate = candidates[0]
    assert isinstance(candidate, CandidateIssuance)
    assert candidate.source_regulator == "IC"
    assert candidate.issuance_identifier == "CL No. 2026-08"
