import pytest
from core.parsing import clean_text, make_absolute_url, extract_html_text
from core.exceptions import AdapterFetchError
from core.http_client import ScrapingHttpClient


def test_clean_text_utility():
    dirty = "  Hello \t\n  World!   "
    assert clean_text(dirty) == "Hello World!"


def test_make_absolute_url_utility():
    base = "https://www.bir.gov.ph/index.html"
    relative = "documents/circular.pdf"
    assert make_absolute_url(base, relative) == "https://www.bir.gov.ph/documents/circular.pdf"


def test_extract_html_text_utility():
    html = "<html><body><h1>Title</h1><script>var x=1;</script><p>Content text</p></body></html>"
    extracted = extract_html_text(html)
    assert "Title" in extracted
    assert "Content text" in extracted
    assert "var x=1" not in extracted


def test_http_client_failure_raises_custom_exception():
    client = ScrapingHttpClient(timeout=2, max_retries=1, retry_backoff_sec=0.1)
    with pytest.raises(AdapterFetchError) as exc_info:
        client.fetch_html("TEST_REG", "https://invalid-domain-name-that-does-not-exist-12345.com")
    
    assert exc_info.value.regulator_id == "TEST_REG"
