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
    Adapter for the Insurance Commission (IC). IC's site is WordPress-based,
    but different sections use different page templates (confirmed live,
    2026-09):
      - Circular Letters (/category/circular-letters/): a standard category
        archive, one <article><h2 class="entry-title"> per item.
      - Advisories (/advisories/) and Memorandum Circulars (/memoranda/):
        a page-builder ("Premium Blog") widget -- only one wrapping
        <article> for the whole page, with each item's link instead under
        its own <span class="premium-blog-entry-title">. A parser that only
        looks for one <article> per item (as this adapter previously did)
        finds just one candidate total on these pages, silently missing
        everything else.

    Per Handoff §13, nav labels don't always match URL slugs or issuance
    prefixes, so identifier extraction is regex-based against the visible
    text rather than assumed from page/URL structure.
    """

    BASE_URL = "https://www.insurance.gov.ph"
    DEFAULT_CATEGORY = "IC-CL"

    # Path per category, relative to BASE_URL. Confirmed live, 2026-09 --
    # note memoranda/advisories are NOT under /category/ despite the old
    # nav-label assumption.
    _CATEGORY_PATHS = {
        "IC-CL": "/category/circular-letters/",
        "IC-ADVISORY": "/advisories/",
        "IC-MC": "/memoranda/",
    }

    # IC needs a metered scraping proxy to get past GitHub Actions' IP block
    # (see core/http_client.py), and that proxy costs real money per request.
    # Restricting IC to the business day's opening check only (main.py
    # enforces this via OPENING_CHECK_ONLY) keeps proxy usage well within
    # budget across all three IC categories combined with SEC's.
    OPENING_CHECK_ONLY = True

    # Matches "Circular Letter No. 2024-11" / "MC ... 2024-01" / etc.
    _IDENTIFIER_RE = re.compile(
        r"((?:Circular\s+Letter|Memorandum\s+Circular|Advisory|CL|MC|ADV)\s*(?:No\.?)?\s*\d+[-–]\d+)",
        re.IGNORECASE,
    )
    # Matches the letter-prefixed docket format Advisories actually use, e.g.
    # "Advisory No. RS-2026-008" or "... MSS-2026-014" (confirmed live,
    # 2026-09) -- the plain _IDENTIFIER_RE above requires digits right after
    # the prefix and won't match these.
    _DOCKET_IDENTIFIER_RE = re.compile(
        r"(Advisory\s*(?:No\.?)?\s*[A-Z]{2,5}-\d{4}-\d+)",
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
        self.category = (category or self.DEFAULT_CATEGORY).upper()
        path = target_path or self._CATEGORY_PATHS.get(self.category)
        if not path:
            raise ValueError(f"No known IC path for category '{self.category}'.")
        self.target_url = self.BASE_URL + path
        self.http_client = ScrapingHttpClient()

    @property
    def regulator_id(self) -> str:
        return "IC"

    def validate(self, html_content: str) -> bool:
        if not html_content or not html_content.strip():
            return False
        soup = BeautifulSoup(html_content, "html.parser")
        return bool(soup.find("article")) or bool(soup.find("a", href=True))

    def _extract_identifier(self, title: str) -> str:
        docket_match = self._DOCKET_IDENTIFIER_RE.search(title)
        if docket_match:
            return clean_text(docket_match.group(1))

        match = self._IDENTIFIER_RE.search(title)
        if not match:
            return title[:40].strip()

        raw_match = match.group(1)
        number_match = re.search(r"\d+[-–]\d+", raw_match)
        number = number_match.group(0) if number_match else raw_match
        first_word = raw_match.split()[0].lower()
        prefix = self._PREFIX_MAP.get(first_word, first_word.upper())
        return f"{prefix} No. {number}"

    def _find_item_anchors(self, soup: BeautifulSoup) -> List:
        """Finds one anchor per listed item, trying each known IC page
        template in order (see class docstring) before falling back to
        "every link on the page" as a last resort."""
        selectors = ["article h2.entry-title a[href]", "span.premium-blog-entry-title a[href]"]
        for selector in selectors:
            found = soup.select(selector)
            if found:
                return found

        # Fallback 1: one anchor per <article>, however it's laid out inside.
        articles = soup.find_all("article")
        if articles:
            anchors = []
            for article in articles:
                heading = article.find("h2") or article.find("a")
                anchor = heading if (heading and heading.name == "a") else (heading.find("a") if heading else None)
                if anchor and anchor.has_attr("href"):
                    anchors.append(anchor)
            if anchors:
                return anchors

        # Fallback 2: no recognizable per-item structure at all -- every link
        # on the page. Noisier (may include nav/footer links), but better
        # than silently returning nothing if IC's markup changes again.
        return soup.find_all("a", href=True)

    def parse(self, html_content: str) -> List[CandidateIssuance]:
        soup = BeautifulSoup(html_content, "html.parser")
        candidates: List[CandidateIssuance] = []

        for anchor in self._find_item_anchors(soup):
            title_text = clean_text(anchor.get_text())
            href = anchor.get("href")
            if not title_text or not href:
                continue

            candidates.append(
                CandidateIssuance(
                    source_regulator=self.regulator_id,
                    source_category=self.category,
                    issuance_identifier=self._extract_identifier(title_text),
                    issuance_title=title_text,
                    source_url=make_absolute_url(self.target_url, href),
                    raw_content_reference=str(anchor),
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
