import re
from typing import List, Optional
from bs4 import BeautifulSoup

from core.base_adapter import BaseSourceAdapter
from core.http_client import ScrapingHttpClient
from core.logger import setup_logger
from core.models import RawIssuance
from core.parsing import clean_text, make_absolute_url

logger = setup_logger("bir_adapter")

# Fallback default URLs for BIR revenue issuances
DEFAULT_BIR_RMC_URL = "https://www.bir.gov.ph/revenue-issuances-details"
DEFAULT_BASE_URL = "https://www.bir.gov.ph"


class BIRAdapter(BaseSourceAdapter):
    """Adapter for scraping official issuances from the Bureau of Internal Revenue (BIR)."""

    def __init__(self, http_client: Optional[ScrapingHttpClient] = None):
        self.http_client = http_client or ScrapingHttpClient()

    @property
    def regulator_id(self) -> str:
        return "BIR"

    def fetch_latest_issuances(
        self, category_id: str, config: dict
    ) -> List[RawIssuance]:
        """Fetches and parses raw issuances for BIR categories (e.g., RMC, RR)."""
        target_url = config.get("target_url", DEFAULT_BIR_RMC_URL)
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
        """Parses BIR web page HTML content to extract issuance metadata and PDF links."""
        soup = BeautifulSoup(html_content, "html.parser")
        raw_issuances: List[RawIssuance] = []

        # Find all table rows in the document
        rows = soup.find_all("tr")

        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            row_text = " ".join(clean_text(cell.get_text()) for cell in cells)

            # Look for links pointing to PDFs or circular documents
            pdf_url = None
            link_tag = row.find("a", href=True)
            if link_tag:
                href = link_tag["href"]
                pdf_url = make_absolute_url(source_url, href)

            # Skip header or empty rows without actionable titles
            if not row_text or len(row_text) < 10 or "subject" in row_text.lower() and "file" in row_text.lower():
                continue

            # Extract raw identifier (e.g., "RMC No. 15-2026" or "RR No. 2-2026")
            identifier = self._extract_identifier(row_text, category_id)
            title = clean_text(row_text)

            raw_item = RawIssuance(
                regulator_id=self.regulator_id,
                category_id=category_id,
                title=title,
                canonical_url=source_url,
                raw_identifier=identifier,
                pdf_url=pdf_url,
                extracted_text=f"BIR {category_id} document: {title}",
            )
            raw_issuances.append(raw_item)

        return raw_issuances

    def _extract_identifier(self, text: str, category_id: str) -> Optional[str]:
        """Extracts standard BIR issuance identifiers from text using regular expressions."""
        # Regex patterns for RMC, RR, RMO identifiers
        patterns = [
            r"(RMC\s*No\.?\s*\d+[-–]\d+)",
            r"(RR\s*No\.?\s*\d+[-–]\d+)",
            r"(RMO\s*No\.?\s*\d+[-–]\d+)",
            r"(No\.?\s*\d+[-–]\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Normalize spaces (e.g. "RMC No. 15-2026")
                return clean_text(match.group(1))
        return None
