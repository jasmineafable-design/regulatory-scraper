import logging
from typing import List, Optional

from bs4 import BeautifulSoup

from core.adapters.base_adapter import BaseAdapter
from core.exceptions import ParsingError
from core.http_client import ScrapingHttpClient
from core.parsing import clean_text, make_absolute_url
from models.issuance import CandidateIssuance

logger = logging.getLogger(__name__)


class BIRAdapter(BaseAdapter):
    """
    Adapter for the Bureau of Internal Revenue (BIR). BIR is directly accessible
    (no proxy/mirror required) — see Handoff §13.
    """

    DEFAULT_URL = (
        "https://www.bir.gov.ph/index.php/revenue-issuances/"
        "revenue-memorandum-circulars.html"
    )
    DEFAULT_CATEGORY = "RMC"

    def __init__(self, target_url: Optional[str] = None, category: Optional[str] = None):
        self.target_url = target_url or self.DEFAULT_URL
        self.category = category or self.DEFAULT_CATEGORY
        self.http_client = ScrapingHttpClient()

    @property
    def regulator_id(self) -> str:
        return "BIR"

    def validate(self, html_content: str) -> bool:
        """A genuine BIR issuance-listing page contains a table of issuances."""
        if not html_content or not html_content.strip():
            return False
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.find("table") is not None

    def parse(self, html_content: str) -> List[CandidateIssuance]:
        soup = BeautifulSoup(html_content, "html.parser")
        candidates: List[CandidateIssuance] = []

        table = soup.find("table")
        if not table:
            return candidates

        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header row
            cols = row.find_all(["td", "th"])
            if len(cols) < 2:
                continue

            issuance_no = clean_text(cols[0].get_text())
            title_col = cols[1]
            date_str = clean_text(cols[2].get_text()) if len(cols) > 2 else None
            title_text = clean_text(title_col.get_text())

            link_tag = title_col.find("a")
            href = link_tag["href"] if link_tag and link_tag.has_attr("href") else ""
            source_url = make_absolute_url(self.target_url, href) if href else self.target_url

            if not issuance_no or not title_text:
                continue

            # BIR's listing table already includes the full label (e.g. "RMC No.
            # 12-2026") in the first column, per the documented number-year
            # convention (Handoff §13) — use it as-is rather than re-prefixing.
            identifier = issuance_no if issuance_no.upper().startswith(self.category.upper()) else f"{self.category} No. {issuance_no}"

            candidates.append(
                CandidateIssuance(
                    source_regulator=self.regulator_id,
                    source_category=self.category,
                    issuance_identifier=identifier,
                    issuance_title=title_text,
                    source_url=source_url,
                    raw_content_reference=str(row),
                    publication_date=date_str,
                    validation_status="genuine",
                )
            )

        return candidates

    def fetch_latest_issuances(self) -> List[CandidateIssuance]:
        logger.info(f"[{self.regulator_id}] Fetching latest issuances from {self.target_url}...")

        html_content = self.http_client.fetch_html(self.regulator_id, self.target_url)

        if not self.validate(html_content):
            raise ParsingError(
                self.regulator_id,
                "Fetched BIR page did not contain the expected issuance table "
                "(possible block page, CAPTCHA, or site structure change).",
            )

        candidates = self.parse(html_content)
        logger.info(f"[{self.regulator_id}] Extracted {len(candidates)} candidate issuance(s).")
        return candidates
