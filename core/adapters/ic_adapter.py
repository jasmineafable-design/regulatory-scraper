import re
from typing import List, Optional
from bs4 import BeautifulSoup

from core.base_adapter import BaseSourceAdapter
from core.http_client import ScrapingHttpClient
from core.logger import setup_logger
from core.models import RawIssuance
from core.parsing import clean_text, make_absolute_url

logger = setup_logger("ic_adapter")

# Default URLs for IC Categories
CATEGORY_URL_MAP = {
    "CL": "https://www.insurance.gov.ph/category/circular-letters/",
    "ADV": "https://www.insurance.gov.ph/category/advisories/",
    "MC": "https://www.insurance.gov.ph/category/memorandum-circulars/",
}
DEFAULT_IC_URL = "https://www.insurance.gov.ph/category/circular-letters/"


class ICAdapter(BaseSourceAdapter):
    """Adapter for scraping official issuances (CL, Advisories, MC) from the Insurance Commission (IC)."""

    def __init__(self, http_client: Optional[ScrapingHttpClient] = None):
        self.http_client = http_client or ScrapingHttpClient()

    @property
    def regulator_id(self) -> str:
        return "IC"

    def fetch_latest_issuances(
        self, category_id: str, config: dict
    ) -> List[RawIssuance]:
        """Fetches and parses raw issuances for IC categories (CL, ADV, MC)."""
        target_url = config.get("target_url") or CATEGORY_URL_MAP.get(category_id, DEFAULT_IC_URL)
        logger.info(f"[{self.regulator_id}] Scraping category '{category_id}' from {target_url}")

        try:
            html_content = self.http_client.fetch_html(self.regulator_id, target_url)
            raw_issuances = self.parse_html_page(html_content, target_url, category_id)
            logger.info(
                f"[{self.regulator_id}] Successfully extracted {len(raw_issuances)} raw issuances for '{category_id}'"
            )
            return raw_issuances
        except Exception as e:
            logger.error(f"[{self.regulator_id}] Scraping failed for '{category_id}': {e}")
            return []

    def parse_html_page(
        self, html_content: str, source_url: str, category_id: str
    ) -> List[RawIssuance]:
        """Parses IC web page HTML content to extract circular metadata and PDF links."""
        soup = BeautifulSoup(html_content, "html.parser")
        raw_issuances: List[RawIssuance] = []

        # 1. Parse HTML table rows
        rows = soup.find_all("tr")

        for row in rows:
            if row.find_all("th"):
                continue

            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            row_text = " ".join(clean_text(cell.get_text()) for cell in cells)

            pdf_url = None
            link_tag = row.find("a", href=True)
            if link_tag:
                href = link_tag["href"]
                pdf_url = make_absolute_url(source_url, href)

            row_lower = row_text.lower()
            if not row_text or len(row_text) < 10 or "circular no" in row_lower or ("subject" in row_lower and "link" in row_lower):
                continue

            identifier = self._extract_identifier(row_text, category_id)
            title = clean_text(row_text)

            raw_item = RawIssuance(
                regulator_id=self.regulator_id,
                category_id=category_id,
                title=title,
                canonical_url=source_url,
                raw_identifier=identifier,
                pdf_url=pdf_url,
                extracted_text=f"IC {category_id} document: {title}",
            )
            raw_issuances.append(raw_item)

        # 2. Fallback: Parse article/post blocks if not formatted as a table
        if not raw_issuances:
            articles = soup.find_all(["article", "li", "div"], class_=re.compile(r"post|entry|item", re.I))
            for item in articles:
                text = clean_text(item.get_text())
                link_tag = item.find("a", href=True)
                if not text or len(text) < 15 or not link_tag:
                    continue

                pdf_url = make_absolute_url(source_url, link_tag["href"])
                identifier = self._extract_identifier(text, category_id)

                raw_issuances.append(
                    RawIssuance(
                        regulator_id=self.regulator_id,
                        category_id=category_id,
                        title=text,
                        canonical_url=source_url,
                        raw_identifier=identifier,
                        pdf_url=pdf_url,
                        extracted_text=f"IC {category_id} document: {text}",
                    )
                )

        return raw_issuances

    def _extract_identifier(self, text: str, category_id: str) -> Optional[str]:
        """Extracts standard IC identifiers for CL, Advisories, and MCs using regex."""
        patterns = [
            # Circular Letters
            r"(CL\s*No\.?\s*\d+[-–]\d+)",
            r"(Circular\s*Letter\s*No\.?\s*\d+[-–]\d+)",
            # Memorandum Circulars
            r"(MC\s*No\.?\s*\d+[-–]\d+)",
            r"(Memorandum\s*Circular\s*No\.?\s*\d+[-–]\d+)",
            # Advisories
            r"(Advisory\s*No\.?\s*\d+[-–]\d+)",
            r"(IC\s*Advisory\s*No\.?\s*\d+[-–]\d+)",
            # General Fallback
            r"(CL\s*\d+[-–]\d+)",
            r"(MC\s*\d+[-–]\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return clean_text(match.group(1))
        return None
