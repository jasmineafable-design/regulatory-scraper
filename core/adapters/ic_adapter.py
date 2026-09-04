import logging
import os
import re
from typing import List, Optional

from bs4 import BeautifulSoup

from core.adapters.base_adapter import BaseAdapter
from core.exceptions import ParsingError
from core.http_client import ScrapingHttpClient
from core.parsing import clean_text, fallback_identifier as _fallback_identifier, make_absolute_url
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

    # Structures that actually indicate an IC listing page (see class
    # docstring). Used by both validate() and _find_item_anchors so the two
    # can't disagree about what counts as a listing.
    _ITEM_SELECTORS = ("article h2.entry-title a[href]", "span.premium-blog-entry-title a[href]")

    def validate(self, html_content: str) -> bool:
        """True only if the page actually looks like an IC listing.

        Previously this accepted any page containing *a single link*, which
        every error page, proxy block page and CDN interstitial on the
        internet satisfies -- so a 503 page sailed through validation and got
        parsed (see the fallback note in _find_item_anchors).
        """
        if not html_content or not html_content.strip():
            return False
        soup = BeautifulSoup(html_content, "html.parser")
        if any(soup.select(selector) for selector in self._ITEM_SELECTORS):
            return True
        # Some IC templates wrap items in <article> without an entry-title;
        # accept that only if the article actually carries a link.
        return any(article.find("a", href=True) for article in soup.find_all("article"))

    def _extract_identifier(self, title: str, href: str = "") -> str:
        docket_match = self._DOCKET_IDENTIFIER_RE.search(title)
        if docket_match:
            return clean_text(docket_match.group(1))

        match = self._IDENTIFIER_RE.search(title)
        if not match:
            # No parseable issuance number. The old behaviour -- a bare
            # title[:40] -- silently collided whenever two items shared their
            # first 40 characters, which is common for IC's long
            # "Notice to All Insurance Companies Regarding ..." titles. Since
            # state dedupes on this identifier alone, the second item was
            # treated as already-seen and never notified. Appending the URL
            # slug keeps it unique. Well-formed identifiers (the paths above)
            # are untouched, so existing state stays valid.
            return _fallback_identifier(title, href)

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
        for selector in self._ITEM_SELECTORS:
            found = soup.select(selector)
            if found:
                return found

        # Fallback: one anchor per <article>, however it's laid out inside.
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

        # There used to be a second fallback here returning EVERY <a href> on
        # the page, on the reasoning that noise beats silence if IC's markup
        # changes. In practice it was worse than silence: combined with the
        # old permissive validate(), an IC error/block page (which has links
        # but no listing) parsed cleanly into ~5 "issuances" named "Home",
        # "About Us", "Contact", "Privacy Policy", "Facebook". On a
        # first-ever run those get written into state as BASELINE records,
        # permanently polluting it; on later runs they'd be emailed to
        # recipients as regulatory issuances. Returning nothing here lets
        # fetch_latest_issuances raise ParsingError instead, which fails loud
        # (§3.8) and is diagnosable.
        return []

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
                    issuance_identifier=self._extract_identifier(title_text, href),
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
        if not candidates:
            # The page validated as a listing but yielded nothing. That's
            # either a genuinely empty category or a markup drift, and the two
            # are indistinguishable from here -- so warn loudly rather than
            # raise (a real empty category must not fail the whole workflow
            # every day) and rather than log at INFO (which reads as a normal
            # "no updates" result).
            logger.warning(
                f"[{self.regulator_id}/{self.category}] Page validated as a listing but "
                f"0 candidates were extracted from {self.target_url}. If this category is "
                "not genuinely empty, IC's markup has drifted and the selectors in "
                "_ITEM_SELECTORS need rechecking."
            )
        else:
            logger.info(
                f"[{self.regulator_id}/{self.category}] Extracted {len(candidates)} candidate issuance(s)."
            )
        return candidates
