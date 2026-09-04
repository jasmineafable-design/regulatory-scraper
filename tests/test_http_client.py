from unittest.mock import MagicMock, patch

import pytest
import requests

from core.exceptions import AdapterFetchError
from core.http_client import ScrapingHttpClient


def _http_error(status_code: int) -> requests.exceptions.HTTPError:
    response = MagicMock()
    response.status_code = status_code
    return requests.exceptions.HTTPError(response=response)


def test_proxy_call_retries_transient_error_up_to_budget(monkeypatch):
    monkeypatch.setenv("SCRAPER_PROXY_API_KEY", "test-key")
    client = ScrapingHttpClient(retry_backoff_sec=0)

    with patch.object(client.session, "get", side_effect=_http_error(503)) as mock_get:
        with pytest.raises(AdapterFetchError):
            client.fetch_html("IC", "https://www.insurance.gov.ph/test", use_proxy=True)

    # Was asserted as 2, on the mistaken premise that every proxy attempt costs
    # a credit. ScraperAPI bills only successful (200/404) responses, so
    # retrying a 5xx is free -- the budget is spent on success odds instead.
    assert mock_get.call_count == ScrapingHttpClient.PROXY_MAX_RETRIES == 4


def test_proxy_call_does_not_retry_non_transient_error(monkeypatch):
    monkeypatch.setenv("SCRAPER_PROXY_API_KEY", "test-key")
    client = ScrapingHttpClient(retry_backoff_sec=0)

    with patch.object(client.session, "get", side_effect=_http_error(404)) as mock_get:
        with pytest.raises(AdapterFetchError):
            client.fetch_html("IC", "https://www.insurance.gov.ph/test", use_proxy=True)

    # A 404 will fail identically every time -- retrying just wastes a credit.
    assert mock_get.call_count == 1


def test_proxy_call_does_retry_on_429(monkeypatch):
    monkeypatch.setenv("SCRAPER_PROXY_API_KEY", "test-key")
    client = ScrapingHttpClient(retry_backoff_sec=0)

    with patch.object(client.session, "get", side_effect=_http_error(429)) as mock_get:
        with pytest.raises(AdapterFetchError):
            client.fetch_html("IC", "https://www.insurance.gov.ph/test", use_proxy=True)

    assert mock_get.call_count == ScrapingHttpClient.PROXY_MAX_RETRIES


def test_proxy_500_recovers_within_retry_budget(monkeypatch):
    """The actual production failure (2026-09-04): ScraperAPI returned 500 --
    its own ~70s proxy-rotation window giving up -- on 4 of 7 IC/SEC
    categories. Two attempts weren't enough; a third or fourth is free and
    usually succeeds."""
    monkeypatch.setenv("SCRAPER_PROXY_API_KEY", "test-key")
    client = ScrapingHttpClient(retry_backoff_sec=0)

    ok = MagicMock()
    ok.text = "<html><a href='/x'>Circular Letter No. 2026-01</a></html>"
    ok.raise_for_status.return_value = None
    side_effect = [_http_error(500), _http_error(500), ok]

    with patch.object(client.session, "get", side_effect=side_effect) as mock_get:
        html = client.fetch_html("IC", "https://www.insurance.gov.ph/test", use_proxy=True)

    assert "Circular Letter" in html
    assert mock_get.call_count == 3


def test_proxy_call_uses_timeout_above_scraperapi_internal_window(monkeypatch):
    """ScraperAPI retries internally for ~70s before returning 500; a client
    timeout under that aborts requests that were still on track."""
    monkeypatch.setenv("SCRAPER_PROXY_API_KEY", "test-key")
    client = ScrapingHttpClient(retry_backoff_sec=0)

    ok = MagicMock()
    ok.text = "<html></html>"
    ok.raise_for_status.return_value = None

    with patch.object(client.session, "get", return_value=ok) as mock_get:
        client.fetch_html("IC", "https://www.insurance.gov.ph/test", use_proxy=True)

    assert mock_get.call_args.kwargs["timeout"] >= 70


def test_proxy_country_code_is_opt_in(monkeypatch):
    """Country-specific geotargeting is a paid ScraperAPI feature, so it must
    only be sent when explicitly configured."""
    monkeypatch.setenv("SCRAPER_PROXY_API_KEY", "test-key")
    monkeypatch.delenv("SCRAPER_PROXY_COUNTRY_CODE", raising=False)
    client = ScrapingHttpClient(retry_backoff_sec=0)

    ok = MagicMock()
    ok.text = "<html></html>"
    ok.raise_for_status.return_value = None

    with patch.object(client.session, "get", return_value=ok) as mock_get:
        client.fetch_html("IC", "https://www.insurance.gov.ph/test", use_proxy=True)
    assert "country_code" not in mock_get.call_args.kwargs["params"]

    monkeypatch.setenv("SCRAPER_PROXY_COUNTRY_CODE", "ph")
    with patch.object(client.session, "get", return_value=ok) as mock_get:
        client.fetch_html("IC", "https://www.insurance.gov.ph/test", use_proxy=True)
    assert mock_get.call_args.kwargs["params"]["country_code"] == "ph"


def test_non_proxy_call_still_uses_full_retry_budget():
    client = ScrapingHttpClient(retry_backoff_sec=0, max_retries=3)

    with patch.object(client.session, "get", side_effect=_http_error(503)) as mock_get:
        with pytest.raises(AdapterFetchError):
            client.fetch_html("BIR", "https://www.bir.gov.ph/test", use_proxy=False)

    # Direct (non-metered) fetches keep the original retry budget.
    assert mock_get.call_count == 3
