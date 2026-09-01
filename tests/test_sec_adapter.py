import pytest

from core.adapters.sec_adapter import SECAdapter
from core.exceptions import ParsingError
from models.issuance import CandidateIssuance

# Confirmed live structure (2026-09, via real browser session against
# www.sec.gov.ph -- see core/adapters/sec_adapter.py docstring):
# <h2 class="entry-title"><a href="..."><b>IDENTIFIER</b><br>TITLE</a></h2>
SAMPLE_SEC_MC_HTML = """
<html><body>
    <h2 class="entry-title">
        <a href="https://www.sec.gov.ph/mc-2026/sec-mc-no-24-series-of-2026/">
            <b>SEC MC No. 24, series of 2026</b><br>MANDATORY USE OF THE ONLINE APPLICATION
        </a>
    </h2>
</body></html>
"""

SAMPLE_SEC_RESOLUTION_HTML = """
<html><body>
    <h2 class="entry-title">
        <a href="https://www.sec.gov.ph/resolution-2026/sec-eipd-case-no-2025-8063/">
            <b>SEC EIPD Case No. 2025-8063</b><br>Resolution upholding the Revocation Order
        </a>
    </h2>
</body></html>
"""


def test_sec_adapter_regulator_id():
    assert SECAdapter().regulator_id == "SEC"


def test_sec_adapter_targets_main_site_not_the_dead_appointment_mirror():
    # Correction (2026-09): appointment.sec.gov.ph turned out to be an
    # unrelated appointment-booking site, not a working mirror. The real
    # content lives on www.sec.gov.ph, reached via the scraping proxy (like
    # IC) since the main site blocks datacenter IPs at the network level.
    adapter = SECAdapter()
    assert "www.sec.gov.ph" in adapter.target_url
    assert "appointment.sec.gov.ph" not in adapter.target_url


def test_sec_adapter_is_opening_check_only():
    # Shares IC's metered-proxy budget -- must not fetch on every recurring
    # run (see main.py's OPENING_CHECK_ONLY enforcement).
    assert SECAdapter().OPENING_CHECK_ONLY is True


def test_sec_adapter_default_category_is_mc():
    adapter = SECAdapter()
    assert adapter.category == "SEC-MC"
    assert "/mc-" in adapter.target_url


def test_sec_adapter_resolution_category_targets_resolution_path():
    adapter = SECAdapter(category="SEC-RESOLUTION")
    assert "/category/resolution-" in adapter.target_url


def test_sec_adapter_parse_produces_candidate_issuances():
    adapter = SECAdapter()
    candidates = adapter.parse(SAMPLE_SEC_MC_HTML)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert isinstance(candidate, CandidateIssuance)
    assert candidate.source_regulator == "SEC"
    assert candidate.issuance_identifier == "SEC MC No. 24, series of 2026"


def test_sec_adapter_parse_resolution_docket_identifier():
    adapter = SECAdapter(category="SEC-RESOLUTION")
    candidates = adapter.parse(SAMPLE_SEC_RESOLUTION_HTML)

    assert len(candidates) == 1
    assert candidates[0].issuance_identifier == "SEC EIPD Case No. 2025-8063"
    assert candidates[0].source_category == "SEC-RESOLUTION"


def test_sec_adapter_fetch_latest_issuances_uses_http_client(monkeypatch):
    adapter = SECAdapter()
    monkeypatch.setattr(adapter.http_client, "fetch_html", lambda regulator_id, url, use_proxy=False: SAMPLE_SEC_MC_HTML)

    candidates = adapter.fetch_latest_issuances()

    assert len(candidates) == 1
    assert candidates[0].source_regulator == "SEC"


def test_sec_adapter_raises_on_empty_response(monkeypatch):
    adapter = SECAdapter()
    monkeypatch.setattr(adapter.http_client, "fetch_html", lambda regulator_id, url, use_proxy=False: "")

    with pytest.raises(ParsingError):
        adapter.fetch_latest_issuances()
