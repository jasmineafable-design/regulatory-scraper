import time
import requests
from typing import Optional
from core.exceptions import AdapterFetchError
from core.logger import setup_logger

logger = setup_logger("http_client")

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

    def fetch_html(self, regulator_id: str, url: str) -> str:
        """Fetches web page HTML text with retry mechanism."""
        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                logger.info(f"[{regulator_id}] Fetching URL (Attempt {attempt}/{self.max_retries}): {url}")
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
