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
    monkeypatch.setattr(
        adapter.http_client,
        "fetch_html",
        lambda regulator_id, url, use_proxy=False: SAMPLE_IC_ARTICLE_HTML,
    )

    candidates = adapter.fetch_latest_issuances()

    assert len(candidates) == 2
    assert all(c.source_regulator == "IC" for c in candidates)


def test_ic_adapter_raises_on_empty_response(monkeypatch):
    adapter = ICAdapter()
    monkeypatch.setattr(adapter.http_client, "fetch_html", lambda regulator_id, url, use_proxy=False: "")

    with pytest.raises(ParsingError):
        adapter.fetch_latest_issuances()


def test_ic_adapter_uses_proxy_when_key_configured(monkeypatch):
    """SCRAPER_PROXY_API_KEY being set should make the adapter request the
    proxy path -- this is what actually gets IC past GitHub Actions' IP block."""
    adapter = ICAdapter()
    monkeypatch.setenv("SCRAPER_PROXY_API_KEY", "fake-key-for-test")

    captured = {}

    def fake_fetch_html(regulator_id, url, use_proxy=False):
        captured["use_proxy"] = use_proxy
        return SAMPLE_IC_ARTICLE_HTML

    monkeypatch.setattr(adapter.http_client, "fetch_html", fake_fetch_html)
    adapter.fetch_latest_issuances()

    assert captured["use_proxy"] is True


# Confirmed live structure (2026-09): /advisories/ and /memoranda/ use a
# page-builder widget with only one wrapping <article> for the whole page,
# and per-item links under span.premium-blog-entry-title instead.
SAMPLE_IC_PREMIUM_BLOG_HTML = """
<html><body>
    <article>
        <span class="premium-blog-entry-title">
            <a href="/advisory-no-rs-2026-008/">Advisory No. RS-2026-008 | Designation of Officer-in-Charge</a>
        </span>
        <span class="premium-blog-entry-title">
            <a href="/imc-2024-01/">IMC 2024-01 | Increase in the Benefits for Compulsory Motor Vehicle Insurance</a>
        </span>
    </article>
</body></html>
"""


def test_ic_adapter_category_paths():
    assert ICAdapter(category="IC-ADVISORY").target_url == "https://www.insurance.gov.ph/advisories/"
    assert ICAdapter(category="IC-MC").target_url == "https://www.insurance.gov.ph/memoranda/"


def test_ic_adapter_parses_premium_blog_template():
    # Regression test: the old article-per-item-only parser found just one
    # candidate total on this template (the page's single wrapping
    # <article>), silently missing every item after the first.
    adapter = ICAdapter(category="IC-ADVISORY")
    candidates = adapter.parse(SAMPLE_IC_PREMIUM_BLOG_HTML)

    assert len(candidates) == 2
    assert candidates[0].issuance_identifier == "Advisory No. RS-2026-008"


def test_ic_adapter_extracts_docket_style_advisory_identifier():
    adapter = ICAdapter()
    identifier = adapter._extract_identifier("Advisory No. RS-2026-008 | Designation of Officer-in-Charge")
    assert identifier == "Advisory No. RS-2026-008"


def test_ic_adapter_skips_proxy_when_key_not_configured(monkeypatch):
    adapter = ICAdapter()
    monkeypatch.delenv("SCRAPER_PROXY_API_KEY", raising=False)

    captured = {}

    def fake_fetch_html(regulator_id, url, use_proxy=False):
        captured["use_proxy"] = use_proxy
        return SAMPLE_IC_ARTICLE_HTML

    monkeypatch.setattr(adapter.http_client, "fetch_html", fake_fetch_html)
    adapter.fetch_latest_issuances()

    assert captured["use_proxy"] is False
