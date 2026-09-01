import logging
import os
import re
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

    Correction (2026-09): the previously "documented mirror"
    (appointment.sec.gov.ph) is not a mirror of SEC issuances at all -- it's
    the unrelated SEC Appointment Booking System, and its old /mc-{year}/
    path returns nothing. The real, current content lives on the main site
    (www.sec.gov.ph), confirmed live via a real browser session:
      - Memorandum Circulars: /mc-{year}/
      - Resolutions:          /category/resolution-{year}/
      - (Opinions/Decisions exist at /category/opinion-{year}/ and
        /category/decision-{year}/ respectively, not yet wired up here --
        see the ScraperAPI free-tier budget note below.)

    www.sec.gov.ph itself blocks requests from datacenter/cloud IP ranges at
    the network level (confirmed: a plain server-side request to it doesn't
    even get a response) -- the same class of block IC has (see
    core/adapters/ic_adapter.py), not a JS-rendering issue. So, like IC, SEC
    must go through the scraping proxy and is opening-check-only to keep
    proxy usage inside ScraperAPI's free tier: IC (1 category) + SEC-MC +
    SEC-Resolution = 3 opening-check-only categories, ~66 requests/month,
    comfortably under the ~100/month free-tier ceiling. Adding Opinions
    and/or Decisions later will need a paid ScraperAPI plan (or dropping a
    category) to stay within budget.
    """

    MAIN_BASE_URL = "https://www.sec.gov.ph"
    DEFAULT_CATEGORY = "SEC-MC"

    # SEC needs the metered scraping proxy for the same reason IC does (IP
    # block, not bot-detection headers) -- see core/http_client.py and the
    # module docstring above. Restricting to the opening check only keeps
    # proxy usage within the free tier.
    OPENING_CHECK_ONLY = True

    # Path template per category, relative to MAIN_BASE_URL. {year} is filled
    # in with the current year at fetch time.
    _CATEGORY_PATHS = {
        "SEC-MC": "/mc-{year}/",
        "SEC-RESOLUTION": "/category/resolution-{year}/",
    }

    def __init__(self, target_url: Optional[str] = None, category: Optional[str] = None, year: Optional[int] = None):
        self.category = (category or self.DEFAULT_CATEGORY).upper()
        self.year = year or datetime.now().year
        path_template = self._CATEGORY_PATHS.get(self.category)
        if target_url:
            self.target_url = target_url
        elif path_template:
            self.target_url = self.MAIN_BASE_URL + path_template.format(year=self.year)
        else:
            raise ValueError(f"No known SEC path template for category '{self.category}'.")
        self.http_client = ScrapingHttpClient()

    @property
    def regulator_id(self) -> str:
        return "SEC"

    def validate(self, html_content: str) -> bool:
        if not html_content or not html_content.strip():
            return False
        soup = BeautifulSoup(html_content, "html.parser")
        return bool(soup.find_all("a", href=True))

    def _extract_identifier(self, bold_text: str, fallback_title: str) -> str:
        bold_text = clean_text(bold_text)
        if bold_text:
            return bold_text
        # Fallback if the <b> identifier tag isn't present for some entry --
        # take the leading "SEC ... No. ..." / docket-style prefix if we can
        # find one, otherwise a truncated title so we still get *something*
        # stable-ish rather than dropping the item entirely.
        match = re.match(r"^(SEC[^.:]*\d[\d-]*)", fallback_title, re.IGNORECASE)
        return match.group(1).strip() if match else fallback_title[:40].strip()

    def parse(self, html_content: str) -> List[CandidateIssuance]:
        soup = BeautifulSoup(html_content, "html.parser")
        candidates: List[CandidateIssuance] = []

        # Confirmed live structure (2026-09, via real browser session):
        # <h2 class="entry-title"><a href="..."><b>IDENTIFIER</b><br>TITLE</a></h2>
        headings = soup.find_all("h2", class_="entry-title")
        # Fall back to any entry-title-like heading if the exact class ever
        # drifts, rather than silently returning zero candidates.
        if not headings:
            headings = soup.find_all("h2")

        for heading in headings:
            anchor = heading.find("a", href=True)
            if not anchor:
                continue

            bold = anchor.find("b")
            bold_text = bold.get_text() if bold else ""
            full_text = clean_text(anchor.get_text(" ", strip=True))
            title_text = clean_text(full_text[len(bold_text):]) if bold_text else full_text
            if not title_text:
                title_text = full_text

            identifier = self._extract_identifier(bold_text, full_text)
            if not identifier or not full_text:
                continue

            candidates.append(
                CandidateIssuance(
                    source_regulator=self.regulator_id,
                    source_category=self.category,
                    issuance_identifier=identifier,
                    issuance_title=title_text or full_text,
                    source_url=make_absolute_url(self.target_url, anchor["href"]),
                    raw_content_reference=str(heading),
                    validation_status="genuine",
                )
            )

        return candidates

    def fetch_latest_issuances(self) -> List[CandidateIssuance]:
        logger.info(f"[{self.regulator_id}] Fetching latest issuances from {self.target_url}...")

        html_content = self.http_client.fetch_html(
            self.regulator_id, self.target_url, use_proxy=bool(os.getenv("SCRAPER_PROXY_API_KEY"))
        )

        if not self.validate(html_content):
            raise ParsingError(
                self.regulator_id,
                "Fetched SEC page contained no recognizable links "
                "(possible block page or site structure change).",
            )

        candidates = self.parse(html_content)
        logger.info(f"[{self.regulator_id}] Extracted {len(candidates)} candidate issuance(s).")
        return candidates
