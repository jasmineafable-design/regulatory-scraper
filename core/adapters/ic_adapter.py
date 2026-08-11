import logging
import os
import re
from typing import List, Optional

from bs4 import BeautifulSoup

from core.adapters.base_adapter import BaseAdapter
from core.exceptions import ParsingError
from core.http_client import ScrapingHttpClient
from core.parsing import clean_text, make_absolute_url
from models.issuance import CandidateIssuance

logger = logging.getLogger(__name__)


class ICAdapter(BaseAdapter):
    """
    Adapter for the Insurance Commission (IC). IC's site is a WordPress
    category-archive; per Handoff §13 its nav label doesn't always match its URL
    slug or issuance prefix, so identifier extraction is regex-based against the
    visible text rather than assumed from the page structure.
    """

    BASE_URL = "https://www.insurance.gov.ph"
    DEFAULT_PATH = "/category/circular-letters/"
    DEFAULT_CATEGORY = "IC-CL"

    _IDENTIFIER_RE = re.compile(
        r"((?:Circular\s+Letter|Memorandum\s+Circular|Advisory|CL|MC|ADV)\s*(?:No\.?)?\s*\d+[-–]\d+)",
        re.IGNORECASE,
    )
    _PREFIX_MAP = {
        "circular": "CL",
        "memorandum": "MC",
        "advisory": "ADV",
        "cl": "CL",
        "mc": "MC",
        "adv": "ADV",
    }

    def __init__(self, target_path: Optional[str] = None, category: Optional[str] = None):
        self.target_url = self.BASE_URL + (target_path or self.DEFAULT_PATH)
        self.category = category or self.DEFAULT_CATEGORY
        self.http_client = ScrapingHttpClient()

    @property
    def regulator_id(self) -> str:
        return "IC"

    def validate(self, html_content: str) -> bool:
        if not html_content or not html_content.strip():
            return False
        soup = BeautifulSoup(html_content, "html.parser")
        # A genuine category-archive page has at least one article/listing anchor.
        return bool(soup.find("article")) or bool(soup.find("a", href=True))

    def _extract_identifier(self, title: str) -> str:
        match = self._IDENTIFIER_RE.search(title)
        if not match:
            return title[:40].strip()

        raw_match = match.group(1)
        number_match = re.search(r"\d+[-–]\d+", raw_match)
        number = number_match.group(0) if number_match else raw_match
        first_word = raw_match.split()[0].lower()
        prefix = self._PREFIX_MAP.get(first_word, first_word.upper())
        return f"{prefix} No. {number}"

    def parse(self, html_content: str) -> List[CandidateIssuance]:
        soup = BeautifulSoup(html_content, "html.parser")
        candidates: List[CandidateIssuance] = []

        articles = soup.find_all("article")
        items = articles if articles else soup.find_all("a", href=True)

        for item in items:
            if articles:
                heading = item.find("h2") or item.find("a")
                if not heading:
                    continue
                anchor = heading if heading.name == "a" else heading.find("a")
            else:
                heading = item
                anchor = item

            if not heading or not anchor or not anchor.has_attr("href"):
                continue

            title_text = clean_text(heading.get_text())
            href = anchor["href"]
            if not title_text or not href:
                continue

            candidates.append(
                CandidateIssuance(
                    source_regulator=self.regulator_id,
                    source_category=self.category,
                    issuance_identifier=self._extract_identifier(title_text),
                    issuance_title=title_text,
                    source_url=make_absolute_url(self.target_url, href),
                    raw_content_reference=str(item),
                    validation_status="genuine",
                )
            )

        return candidates

    def fetch_latest_issuances(self) -> List[CandidateIssuance]:
        logger.info(f"[{self.regulator_id}] Fetching latest issuances from {self.target_url}...")

        # IC blocks requests from GitHub Actions' IP ranges specifically
        # (confirmed via a real workflow run, not guessed) -- see Handoff §13
        # and core/http_client.py. Routing through the proxy costs nothing
        # extra when SCRAPER_PROXY_API_KEY isn't set locally/in tests: this
        # only takes effect if that env var is present.
        html_content = self.http_client.fetch_html(
            self.regulator_id, self.target_url, use_proxy=bool(os.getenv("SCRAPER_PROXY_API_KEY"))
        )

        if not self.validate(html_content):
            raise ParsingError(
                self.regulator_id,
                "Fetched IC page did not contain any recognizable listing "
                "(possible block page or site structure change).",
            )

        candidates = self.parse(html_content)
        logger.info(f"[{self.regulator_id}] Extracted {len(candidates)} candidate issuance(s).")
        return candidates
