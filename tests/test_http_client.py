from unittest.mock import MagicMock, patch

import pytest
import requests

from core.exceptions import AdapterFetchError
from core.http_client import ScrapingHttpClient


def _http_error(status_code: int) -> requests.exceptions.HTTPError:
    response = MagicMock()
    response.status_code = status_code
    return requests.exceptions.HTTPError(response=response)


def test_proxy_call_retries_at_most_twice_on_transient_error(monkeypatch):
    monkeypatch.setenv("SCRAPER_PROXY_API_KEY", "test-key")
    client = ScrapingHttpClient(retry_backoff_sec=0)

    with patch.object(client.session, "get", side_effect=_http_error(503)) as mock_get:
        with pytest.raises(AdapterFetchError):
            client.fetch_html("IC", "https://www.insurance.gov.ph/test", use_proxy=True)

    # PROXY_MAX_RETRIES == 2 -- must not burn a 3rd metered credit retrying.
    assert mock_get.call_count == 2


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

    assert mock_get.call_count == 2


def test_non_proxy_call_still_uses_full_retry_budget():
    client = ScrapingHttpClient(retry_backoff_sec=0, max_retries=3)

    with patch.object(client.session, "get", side_effect=_http_error(503)) as mock_get:
        with pytest.raises(AdapterFetchError):
            client.fetch_html("BIR", "https://www.bir.gov.ph/test", use_proxy=False)

    # Direct (non-metered) fetches keep the original retry budget.
    assert mock_get.call_count == 3
