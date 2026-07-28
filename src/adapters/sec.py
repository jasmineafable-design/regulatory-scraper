# Location: src/adapters/sec.py (or core/adapters/sec_adapter.py)

import logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("sec_adapter")

class CandidateIssuance:
    def __init__(self, source_regulator: str, issuance_identifier: str, title: str, link: str, date_posted: str = ""):
        self.source_regulator = source_regulator
        self.issuance_identifier = issuance_identifier
        self.title = title
        self.link = link
        self.date_posted = date_posted

class SECAdapter:
    BASE_URL = "https://www.sec.gov.ph"  # Match test requirement

    def __init__(self):
        self.source_regulator = "SEC"
        self.base_url = self.BASE_URL
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.sec.gov.ph/",
        }

    def fetch(self):
        """Standard adapter interface alias expected by unit tests."""
        return self.fetch_latest_issuances()

    def fetch_latest_issuances(self):
        current_year = datetime.now().year
        url = f"{self.base_url}/mc-{current_year}/"
        logger.info(f"Fetching SEC issuances from {url}...")
        
        candidates = []
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.find_all("a", href=True):
                href = anchor["href"]
                text = anchor.get_text(strip=True)
                if href.endswith(".pdf") or "MC-NO" in text.upper() or "MEMORANDUM" in text.upper():
                    identifier = text if text else href.split("/")[-1]
                    candidates.append(
                        CandidateIssuance(
                            source_regulator=self.source_regulator,
                            issuance_identifier=identifier,
                            title=text or identifier,
                            link=href if href.startswith("http") else f"{self.base_url}{href}"
                        )
                    )
            logger.info(f"Successfully extracted {len(candidates)} candidates from SEC.")
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to fetch SEC issuances: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in SEC adapter: {e}")

        return candidates
