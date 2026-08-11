import pytest

from core.adapters.ic_adapter import ICAdapter
from core.exceptions import ParsingError
from models.issuance import CandidateIssuance

SAMPLE_IC_ARTICLE_HTML = """
<html><body>
    <article>
        <h2><a href="/circular-letter-no-2026-08.pdf">Circular Letter No. 2026-08: Guidelines on Microinsurance</a></h2>
    </article>
    <article>
        <h2><a href="/circular-letter-no-2026-07.pdf">Circular Letter No. 2026-07: Risk Capital Requirements</a></h2>
    </article>
</body></html>
"""


def test_ic_adapter_regulator_id():
    assert ICAdapter().regulator_id == "IC"


def test_ic_adapter_default_target_url():
    adapter = ICAdapter()
    assert adapter.target_url == "https://www.insurance.gov.ph/category/circular-letters/"


def test_ic_adapter_identifier_extraction():
    adapter = ICAdapter()
    assert adapter._extract_identifier("Circular Letter No. 2026-08: Guidelines") == "CL No. 2026-08"


def test_ic_adapter_parse_produces_candidate_issuances():
    adapter = ICAdapter()
    candidates = adapter.parse(SAMPLE_IC_ARTICLE_HTML)

    assert len(candidates) == 2
    first = candidates[0]
    assert isinstance(first, CandidateIssuance)
    assert first.source_regulator == "IC"
    assert first.source_category == "IC-CL"
    assert first.issuance_identifier == "CL No. 2026-08"


def test_ic_adapter_fetch_latest_issuances_uses_http_client(monkeypatch):
    adapter = ICAdapter()
    monkeypatch.setattr(adapter.http_client, "fetch_html", lambda regulator_id, url: SAMPLE_IC_ARTICLE_HTML)

    candidates = adapter.fetch_latest_issuances()

    assert len(candidates) == 2
    assert all(c.source_regulator == "IC" for c in candidates)


def test_ic_adapter_raises_on_empty_response(monkeypatch):
    adapter = ICAdapter()
    monkeypatch.setattr(adapter.http_client, "fetch_html", lambda regulator_id, url: "")

    with pytest.raises(ParsingError):
        adapter.fetch_latest_issuances()
