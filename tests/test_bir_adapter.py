import pytest

from core.adapters.bir_adapter import BIRAdapter, BIR_TEMPLATE_IDS
from core.exceptions import ParsingError
from models.issuance import CandidateIssuance

# A trimmed version of the HTML blob BIR's own API returns in
# data[0]["content"]["Content"] -- confirmed via the predecessor system's
# real DevTools capture (see bir_adapter.py's module docstring). This is
# exactly the table body, since the API hands back rich text, not a page.
FIXTURE_TABLE_HTML = """
<table>
  <tbody>
    <tr>
      <td>RMC No. 12-2026</td>
      <td><a href="https://www.bir.gov.ph/images/bir_files/rmc12-2026.pdf" title="Full Text">Full Text</a>
          Clarifying Tax Rules on Digital Transactions</td>
      <td>February 10, 2026</td>
    </tr>
    <tr>
      <td>RMC No. 11-2026</td>
      <td><a href="https://www.bir.gov.ph/images/bir_files/rmc11-2026.pdf" title="Full Text">Full Text</a>
          Filing Guidelines for Annual Information Returns</td>
      <td>January 28, 2026</td>
    </tr>
  </tbody>
</table>
"""


def _fake_payload(category_label: str = "revenue memorandum circular") -> dict:
    return {
        "data": [
            {
                "name": category_label,
                "content": {"Content": FIXTURE_TABLE_HTML},
            }
        ]
    }


def test_bir_adapter_regulator_id():
    assert BIRAdapter().regulator_id == "BIR"


def test_bir_adapter_fetch_latest_issuances_parses_api_response(monkeypatch):
    adapter = BIRAdapter(category="RMC")
    monkeypatch.setattr(
        adapter.http_client, "fetch_json", lambda regulator_id, url, extra_headers=None: _fake_payload()
    )

    candidates = adapter.fetch_latest_issuances()

    assert len(candidates) == 2
    first = candidates[0]
    assert isinstance(first, CandidateIssuance)
    assert first.source_regulator == "BIR"
    assert first.source_category == "RMC"
    assert first.issuance_identifier == "RMC No. 12-2026"
    assert first.source_url.startswith("https://www.bir.gov.ph/")
    assert first.validation_status == "genuine"


def test_bir_adapter_raises_when_api_returns_no_dataset(monkeypatch):
    adapter = BIRAdapter(category="RMC")
    monkeypatch.setattr(
        adapter.http_client, "fetch_json", lambda regulator_id, url, extra_headers=None: {"data": []}
    )

    with pytest.raises(ParsingError):
        adapter.fetch_latest_issuances()


def test_bir_adapter_raises_when_template_id_label_does_not_match_category(monkeypatch):
    """Guards against BIR silently reassigning a template_id to a different
    category -- must fail loud rather than mislabel another category's
    issuances as RMC."""
    adapter = BIRAdapter(category="RMC")
    monkeypatch.setattr(
        adapter.http_client,
        "fetch_json",
        lambda regulator_id, url, extra_headers=None: _fake_payload(category_label="revenue regulation"),
    )

    with pytest.raises(ParsingError):
        adapter.fetch_latest_issuances()


def test_bir_adapter_raises_for_unknown_category():
    adapter = BIRAdapter(category="NOT-A-REAL-CATEGORY")
    with pytest.raises(ParsingError):
        adapter.fetch_latest_issuances()


def test_bir_template_ids_cover_default_category():
    assert BIRAdapter.DEFAULT_CATEGORY in BIR_TEMPLATE_IDS
