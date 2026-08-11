import os
import time
import requests
from typing import Optional
from core.exceptions import AdapterFetchError
from core.logger import setup_logger

logger = setup_logger("http_client")

# Some sources (currently: IC) block requests from GitHub Actions' IP ranges
# specifically, even though they serve normal browsers and other cloud IPs
# fine (confirmed via a real workflow run by the predecessor system). Routing
# just those requests through a scraping proxy is the documented fix -- see
# docs/Regulatory-Scraper-Implementation-Handoff.md §13. Only sources that
# actually need it should set use_proxy=True in fetch_html, to keep proxy
# usage (and cost, on metered free tiers) down.
SCRAPER_PROXY_BASE_URL = "https://api.scraperapi.com/"

# Standard web browser user-agent header to avoid being blocked as a bot
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class ScrapingHttpClient:
    """Robust HTTP client with built-in retries, timeouts, and user-agent spoofing."""

    def __init__(self, timeout: int = 15, max_retries: int = 3, retry_backoff_sec: float = 2.0):
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_sec = retry_backoff_sec
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch_html(self, regulator_id: str, url: str, use_proxy: bool = False) -> str:
        """Fetches web page HTML text with retry mechanism.

        use_proxy=True routes the request through a scraping proxy
        (SCRAPER_PROXY_API_KEY env var) instead of fetching directly -- for
        sources that block requests from GitHub Actions' IP ranges. Fails
        loud (not silently falling back to a direct request) if use_proxy is
        requested but no key is configured, since a direct request to a
        source that's known to block this runner would just fail anyway, in
        a way that's easy to misdiagnose as "site is down."
        """
        if use_proxy:
            api_key = os.getenv("SCRAPER_PROXY_API_KEY", "")
            if not api_key:
                raise AdapterFetchError(
                    regulator_id=regulator_id,
                    url=url,
                    original_error=RuntimeError(
                        "SCRAPER_PROXY_API_KEY is not set, but this source requires the proxy "
                        "(it blocks requests from GitHub Actions' IP ranges directly) -- see "
                        "the README's Google Sheet/secrets section."
                    ),
                )

        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                logger.info(f"[{regulator_id}] Fetching URL (Attempt {attempt}/{self.max_retries}): {url}")
                if use_proxy:
                    response = self.session.get(
                        SCRAPER_PROXY_BASE_URL,
                        params={"api_key": os.getenv("SCRAPER_PROXY_API_KEY", ""), "url": url},
                        timeout=60,
                    )
                else:
                    response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response.text
            except Exception as err:
                last_exception = err
                logger.warning(
                    f"[{regulator_id}] Attempt {attempt} failed for {url}: {err}. "
                    f"Retrying in {self.retry_backoff_sec}s..."
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff_sec)

        raise AdapterFetchError(regulator_id=regulator_id, url=url, original_error=last_exception)

    def fetch_json(self, regulator_id: str, url: str, extra_headers: Optional[dict] = None) -> dict:
        """Fetches and JSON-decodes a URL, with the same retry/backoff as
        fetch_html. extra_headers are merged on top of the session's defaults
        for this one request (some APIs, e.g. BIR's, reject requests that
        don't carry a specific Referer/Origin -- see bir_adapter.py)."""
        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                logger.info(f"[{regulator_id}] Fetching JSON (Attempt {attempt}/{self.max_retries}): {url}")
                response = self.session.get(url, timeout=self.timeout, headers=extra_headers or {})
                response.raise_for_status()
                return response.json()
            except Exception as err:
                last_exception = err
                logger.warning(
                    f"[{regulator_id}] Attempt {attempt} failed for {url}: {err}. "
                    f"Retrying in {self.retry_backoff_sec}s..."
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff_sec)

        raise AdapterFetchError(regulator_id=regulator_id, url=url, original_error=last_exception)
