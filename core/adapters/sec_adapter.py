from typing import List
import requests
from bs4 import BeautifulSoup

from core.adapters.base_adapter import BaseAdapter
from core.models import CandidateIssuance
from core.logger import setup_logger

logger = setup_logger("sec_adapter")


class SECAdapter(BaseAdapter):
    """Adapter for retrieving issuances from the Securities and Exchange Commission (SEC)."""

    regulator_id: str = "SEC"
    default_target_url: str = "https://www.sec.gov.ph/mc-2026/"

    def fetch_latest_issuances(self) -> List[CandidateIssuance]:
        """Fetches and normalizes SEC Memorandum Circulars into standard CandidateIssuance models."""
        logger.info(f"Fetching SEC issuances from {self.default_target_url}...")

        candidates: List[CandidateIssuance] = []

        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            response = requests.get(self.default_target_url, headers=headers, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            for anchor in soup.find_all("a", href=True):
                text = anchor.get_text(strip=True)
                href = anchor["href"]

                if "SEC MC" in text or "Memorandum Circular No." in text:
                    cleaned_id = (
                        text.split(":")[0].strip().replace(" ", "-")
                        if ":" in text
                        else text.replace(" ", "-")
                    )

                    candidate = CandidateIssuance(
                        source_regulator=self.regulator_id,
                        source_category="MC",
                        issuance_identifier=f"SEC-{cleaned_id}",
                        issuance_title=text,
                        source_url=href,
                    )
                    candidates.append(candidate)

        except Exception as e:
            logger.error(f"Failed to fetch SEC issuances: {e}", exc_info=True)

        logger.info(f"Successfully extracted {len(candidates)} candidates from SEC.")
        return candidates
