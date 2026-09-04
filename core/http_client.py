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


def _is_transient(err: Exception) -> bool:
    """Whether a failure is plausibly resolved by retrying (network blip,
    timeout, rate-limit, server-side 5xx) versus a durable failure (4xx other
    than 429, DNS/URL error, etc.) that will just fail identically on retry.

    For proxy (ScraperAPI) calls this also determines whether a retry costs
    anything. ScraperAPI bills only for *successful* responses -- 200 and 404
    -- and explicitly does not charge for the 500 it returns after its own
    internal ~70s retry loop gives up. So a 500 retry is FREE, while a 401/403
    (bad key / out of credits) is both charged-irrelevant and durable. See
    https://docs.scraperapi.com/responses-and-formats/api-status-codes
    """
    if isinstance(err, requests.exceptions.HTTPError):
        status = getattr(err.response, "status_code", None)
        return status == 429 or (status is not None and 500 <= status < 600)
    return isinstance(err, (requests.exceptions.Timeout, requests.exceptions.ConnectionError))


def _is_scraperapi_giveup(err: Exception) -> bool:
    """True for the specific 500 ScraperAPI returns when its own internal
    proxy-rotation retries time out. Purely for accurate logging -- it is
    already covered by _is_transient for retry purposes."""
    return (
        isinstance(err, requests.exceptions.HTTPError)
        and getattr(err.response, "status_code", None) == 500
    )


class ScrapingHttpClient:
    """Robust HTTP client with built-in retries, timeouts, and user-agent spoofing."""

    # Proxy (ScraperAPI) retries are still gated on _is_transient -- a durable
    # 4xx (bad key, out of credits, genuine target-site 404) is never retried.
    # But transient proxy failures are retried MORE than direct fetches, not
    # less: ScraperAPI does not bill failed requests, so a 500 retry costs no
    # credit, and their docs put the baseline failure rate at 1-3% with
    # "in the majority of cases the retry will be successful."
    #
    # Corrected 2026-09-04. The previous value (2) was set on the mistaken
    # premise that every proxy attempt burns a credit; it meant a single
    # opening-check fetch got two shots at a ~flaky-by-design endpoint and
    # then failed the whole workflow. IC and SEC were failing ~4 of 7
    # categories per run for exactly this reason.
    PROXY_MAX_RETRIES = 4

    # ScraperAPI retries internally against different proxies for up to ~70s
    # before returning its 500. A client timeout below that aborts requests
    # that were still on track to succeed -- their docs are explicit that the
    # client timeout must not undercut it.
    PROXY_TIMEOUT_SEC = 75

    def __init__(self, timeout: int = 15, max_retries: int = 3, retry_backoff_sec: float = 2.0):
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_sec = retry_backoff_sec
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _proxy_params(self, url: str) -> dict:
        """Query params for a ScraperAPI call.

        SCRAPER_PROXY_COUNTRY_CODE is optional and unset by default. IC and
        SEC are Philippine government sites that respond slowly and
        inconsistently to the US-region exit nodes ScraperAPI uses by default,
        which is a plausible contributor to the 500s; setting this to "ph"
        routes through a local exit node instead. Left unset because
        country-specific geotargeting is a paid ScraperAPI feature -- sending
        it on a free/hobby plan can itself fail the request, so it must be an
        opt-in only turned on once the plan supports it.
        """
        params = {"api_key": os.getenv("SCRAPER_PROXY_API_KEY", ""), "url": url}
        country_code = os.getenv("SCRAPER_PROXY_COUNTRY_CODE", "").strip()
        if country_code:
            params["country_code"] = country_code
        return params

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

        max_retries = self.PROXY_MAX_RETRIES if use_proxy else self.max_retries
        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt < max_retries:
            attempt += 1
            try:
                logger.info(f"[{regulator_id}] Fetching URL (Attempt {attempt}/{max_retries}): {url}")
                if use_proxy:
                    response = self.session.get(
                        SCRAPER_PROXY_BASE_URL,
                        params=self._proxy_params(url),
                        timeout=self.PROXY_TIMEOUT_SEC,
                    )
                else:
                    response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response.text
            except Exception as err:
                last_exception = err
                if use_proxy and not _is_transient(err):
                    # A durable proxy-relayed failure (bad/exhausted key, or a
                    # genuine 4xx from the target site) fails identically on
                    # retry -- stop rather than hammering it.
                    logger.warning(
                        f"[{regulator_id}] Attempt {attempt} failed for {url}: {err}. "
                        "Not retrying (non-transient failure)."
                    )
                    break

                if use_proxy and _is_scraperapi_giveup(err):
                    # Distinguish "ScraperAPI couldn't reach the target" from
                    # "the target itself errored" -- otherwise a proxy-side
                    # give-up reads as an IC/SEC outage and gets misdiagnosed.
                    logger.warning(
                        f"[{regulator_id}] Attempt {attempt}/{max_retries}: ScraperAPI returned 500 "
                        f"for {url} -- it exhausted its own ~70s proxy-rotation window without a "
                        "successful response. This is a proxy-side give-up, not necessarily a "
                        "target-site outage, and is not billed."
                    )
                else:
                    logger.warning(f"[{regulator_id}] Attempt {attempt}/{max_retries} failed for {url}: {err}.")

                if attempt < max_retries:
                    # Exponential backoff on proxy calls: consecutive immediate
                    # retries tend to land on the same struggling proxy pool,
                    # so widening the gap materially improves the odds the
                    # retry draws a different route.
                    delay = self.retry_backoff_sec * (2 ** (attempt - 1)) if use_proxy else self.retry_backoff_sec
                    logger.warning(f"[{regulator_id}] Retrying in {delay:.0f}s...")
                    time.sleep(delay)

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
