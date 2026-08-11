from pathlib import Path

import pytest

from core.adapters.bir_adapter import BIRAdapter
from core.exceptions import ParsingError
from models.issuance import CandidateIssuance

FIXTURE_HTML = (Path(__file__).parent / "adapters" / "fixtures" / "bir_sample.html").read_text(encoding="utf-8")


def test_bir_adapter_regulator_id():
    assert BIRAdapter().regulator_id == "BIR"


def test_bir_adapter_validate_rejects_empty_or_tableless_content():
    adapter = BIRAdapter()
    assert adapter.validate("") is False
    assert adapter.validate("<html><body>No table here</body></html>") is False
    assert adapter.validate(FIXTURE_HTML) is True


def test_bir_adapter_parse_produces_candidate_issuances():
    adapter = BIRAdapter()
    candidates = adapter.parse(FIXTURE_HTML)

    assert len(candidates) == 2
    first = candidates[0]
    assert isinstance(first, CandidateIssuance)
    assert first.source_regulator == "BIR"
    assert first.source_category == "RMC"
    assert first.issuance_identifier == "RMC No. 12-2026"
    assert first.source_url.startswith("https://www.bir.gov.ph/")
    assert first.validation_status == "genuine"


def test_bir_adapter_fetch_latest_issuances_uses_http_client(monkeypatch):
    adapter = BIRAdapter()
    monkeypatch.setattr(adapter.http_client, "fetch_html", lambda regulator_id, url: FIXTURE_HTML)

    candidates = adapter.fetch_latest_issuances()

    assert len(candidates) == 2
    assert all(c.source_regulator == "BIR" for c in candidates)


def test_bir_adapter_raises_on_invalid_response(monkeypatch):
    adapter = BIRAdapter()
    monkeypatch.setattr(adapter.http_client, "fetch_html", lambda regulator_id, url: "<html>blocked</html>")

    with pytest.raises(ParsingError):
        adapter.fetch_latest_issuances()
