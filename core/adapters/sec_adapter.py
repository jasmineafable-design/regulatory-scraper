import logging
from datetime import datetime
from typing import List, Optional

from bs4 import BeautifulSoup

from core.adapters.base_adapter import BaseAdapter
from core.exceptions import ParsingError
from core.http_client import ScrapingHttpClient
from core.parsing import clean_text, make_absolute_url
from models.issuance import CandidateIssuance

logger = logging.getLogger(__name__)


class SECAdapter(BaseAdapter):
    """
    Adapter for the Securities and Exchange Commission (SEC).

    Per Handoff §13: SEC's main site (www.sec.gov.ph) blocks non-browser requests
    entirely, including from server-side fetch tools. The documented working access
    path is the mirror subdomain appointment.sec.gov.ph, which serves the same
    content. This adapter must use the mirror, not the main site.
    """

    MIRROR_BASE_URL = "https://appointment.sec.gov.ph"
    DEFAULT_CATEGORY = "SEC-MC"

    def __init__(self, target_url: Optional[str] = None, category: Optional[str] = None):
        year = datetime.now().year
        self.target_url = target_url or f"{self.MIRROR_BASE_URL}/mc-{year}/"
        self.category = category or self.DEFAULT_CATEGORY
        self.http_client = ScrapingHttpClient()

    @property
    def regulator_id(self) -> str:
        return "SEC"

    def validate(self, html_content: str) -> bool:
        if not html_content or not html_content.strip():
            return False
        soup = BeautifulSoup(html_content, "html.parser")
        return bool(soup.find_all("a", href=True))

    def parse(self, html_content: str) -> List[CandidateIssuance]:
        soup = BeautifulSoup(html_content, "html.parser")
        candidates: List[CandidateIssuance] = []

        rows = soup.find_all("tr")
        if rows:
            for row in rows:
                anchors = row.find_all("a", href=True)
                if not anchors:
                    continue
                tds = row.find_all("td")
                row_text = clean_text(tds[0].get_text()) if tds else clean_text(row.get_text(" "))
                for anchor in anchors:
                    href = anchor["href"]
                    title_text = row_text or clean_text(anchor.get_text()) or "SEC Issuance"
                    candidates.append(self._build_candidate(title_text, href))
        else:
            for anchor in soup.find_all("a", href=True):
                title_text = clean_text(anchor.get_text())
                if not title_text:
                    continue
                candidates.append(self._build_candidate(title_text, anchor["href"]))

        return candidates

    def _build_candidate(self, title_text: str, href: str) -> CandidateIssuance:
        cleaned_id = title_text.split(":")[0].strip().replace(" ", "-") if ":" in title_text else title_text[:40].replace(" ", "-")
        return CandidateIssuance(
            source_regulator=self.regulator_id,
            source_category=self.category,
            issuance_identifier=f"SEC-{cleaned_id}",
            issuance_title=title_text,
            source_url=make_absolute_url(self.target_url, href),
            raw_content_reference=title_text,
            validation_status="genuine",
        )

    def fetch_latest_issuances(self) -> List[CandidateIssuance]:
        logger.info(f"[{self.regulator_id}] Fetching latest issuances from {self.target_url}...")

        html_content = self.http_client.fetch_html(self.regulator_id, self.target_url)

        if not self.validate(html_content):
            raise ParsingError(
                self.regulator_id,
                "Fetched SEC page contained no recognizable links "
                "(possible block page or site structure change).",
            )

        candidates = self.parse(html_content)
        logger.info(f"[{self.regulator_id}] Extracted {len(candidates)} candidate issuance(s).")
        return candidates
