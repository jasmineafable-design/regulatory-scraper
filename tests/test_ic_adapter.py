from unittest.mock import patch

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


# --- Regression tests, 2026-09-04 IC/SEC fetch-failure review -----------------


BLOCK_PAGE_HTML = """<html><body>
<nav><a href="/">Home</a><a href="/about/">About Us</a><a href="/contact/">Contact</a></nav>
<h1>503 Service Temporarily Unavailable</h1>
<footer><a href="/privacy/">Privacy Policy</a><a href="https://facebook.com/ic">Facebook</a></footer>
</body></html>"""


def test_block_page_does_not_validate_as_a_listing():
    """An error/block page has links but no listing. The old validate()
    accepted any page with a single <a href>, so these passed."""
    assert ICAdapter().validate(BLOCK_PAGE_HTML) is False


def test_block_page_does_not_parse_into_nav_link_issuances():
    """The removed 'every link on the page' fallback turned a block page into
    5 issuances named Home / About Us / Contact / Privacy Policy / Facebook,
    which then got written into state as BASELINE records."""
    assert ICAdapter().parse(BLOCK_PAGE_HTML) == []


def test_block_page_raises_parsing_error_rather_than_reporting_no_updates():
    adapter = ICAdapter()
    with patch.object(adapter.http_client, "fetch_html", return_value=BLOCK_PAGE_HTML):
        with pytest.raises(ParsingError):
            adapter.fetch_latest_issuances()


def test_titles_sharing_first_40_chars_get_distinct_identifiers():
    """State dedupes on issuance_identifier alone, so a bare title[:40]
    fallback made the second of two long-shared-prefix titles look
    already-seen and it was never notified."""
    adapter = ICAdapter()

    def page(href, title):
        return f"<html><article><h2 class='entry-title'><a href='{href}'>{title}</a></h2></article></html>"

    a = adapter.parse(page("/notice-annual-statements/",
                           "Notice to All Insurance Companies Regarding the Submission of Annual Statements"))
    b = adapter.parse(page("/notice-quarterly-reports/",
                           "Notice to All Insurance Companies Regarding the Filing of Quarterly Reports"))

    assert a[0].issuance_identifier != b[0].issuance_identifier


def test_well_formed_identifiers_are_unchanged_by_the_fallback_fix():
    """Existing state keys must stay valid -- only the no-number fallback path
    changed, or every known issuance would re-notify as new."""
    adapter = ICAdapter()
    html = ("<html><article><h2 class='entry-title'>"
            "<a href='/cl-2026-01/'>Circular Letter No. 2026-01 Guidelines</a>"
            "</h2></article></html>")
    assert adapter.parse(html)[0].issuance_identifier == "CL No. 2026-01"
