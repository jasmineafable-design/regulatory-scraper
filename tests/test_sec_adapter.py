import pytest

from core.adapters.sec_adapter import SECAdapter
from core.exceptions import ParsingError
from models.issuance import CandidateIssuance

SAMPLE_SEC_HTML = """
<html><body>
    <a href="/mc-1-2026.pdf">SEC MC No. 1 S. 2026: Rules on Corporate Governance</a>
</body></html>
"""


def test_sec_adapter_regulator_id():
    assert SECAdapter().regulator_id == "SEC"


def test_sec_adapter_uses_mirror_subdomain_not_blocked_main_site():
    adapter = SECAdapter()
    # §13: www.sec.gov.ph blocks non-browser requests; appointment.sec.gov.ph is
    # the documented working mirror. The adapter must never target the main site.
    assert "appointment.sec.gov.ph" in adapter.target_url
    assert "www.sec.gov.ph" not in adapter.target_url


def test_sec_adapter_parse_produces_candidate_issuances():
    adapter = SECAdapter()
    candidates = adapter.parse(SAMPLE_SEC_HTML)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert isinstance(candidate, CandidateIssuance)
    assert candidate.source_regulator == "SEC"
    assert "SEC" in candidate.issuance_identifier


def test_sec_adapter_fetch_latest_issuances_uses_http_client(monkeypatch):
    adapter = SECAdapter()
    monkeypatch.setattr(adapter.http_client, "fetch_html", lambda regulator_id, url: SAMPLE_SEC_HTML)

    candidates = adapter.fetch_latest_issuances()

    assert len(candidates) == 1
    assert candidates[0].source_regulator == "SEC"


def test_sec_adapter_raises_on_empty_response(monkeypatch):
    adapter = SECAdapter()
    monkeypatch.setattr(adapter.http_client, "fetch_html", lambda regulator_id, url: "")

    with pytest.raises(ParsingError):
        adapter.fetch_latest_issuances()
