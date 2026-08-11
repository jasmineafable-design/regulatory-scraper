import logging
import re
from datetime import datetime
from typing import List, Optional

from bs4 import BeautifulSoup

from core.adapters.base_adapter import BaseAdapter
from core.exceptions import ParsingError
from core.http_client import ScrapingHttpClient
from core.parsing import clean_text
from models.issuance import CandidateIssuance

logger = logging.getLogger(__name__)

# BIR's issuance pages (e.g. bir.gov.ph/2026-Revenue-Memorandum-Circulars) are
# JavaScript-rendered -- the page's own HTML has no table to scrape, just a
# "Loading..." placeholder, no matter which URL you point at (confirmed
# 2026-08-11: the old Joomla-style URL this adapter previously used now 404s,
# and the new URL renders nothing without JS). Rendering the page with a
# headless browser would work but is fragile and heavy. Instead, this calls
# the plain JSON API that BIR's own frontend calls to populate that table --
# found via browser DevTools > Network > Fetch/XHR while loading the page,
# and already confirmed working end-to-end by the predecessor system (see
# docs/Regulatory-Scraper-Implementation-Handoff.md §13 and this repo's
# history for that discovery). No bot detection, no rendering, one plain GET.
BIR_DATASET_URL = "https://bir-cms-ws.bir.gov.ph/api/pub/templates/{template_id}/datasets?per_page=3000"

# Each template_id corresponds to one category's *current* content collection
# in BIR's CMS. BIR may reassign a new template_id when it rolls a category
# over to next year's page -- if this starts returning zero results, redo the
# Network-tab check described above to find the new ID (see the label
# sanity-check in fetch_latest_issuances, which warns rather than silently
# using a mismatched ID).
BIR_TEMPLATE_IDS = {
    "RR": 3754,
    "RMC": 3752,
    "RMO": 3753,
}

# BIR's API 403s any request that doesn't look like it came from the matching
# page on bir.gov.ph -- a "client-website-id" header plus a same-site
# Referer/Origin turned out to be the required pieces (User-Agent alone isn't
# enough). Maps each category to the page slug used to build a matching
# Referer.
BIR_REFERER_SLUGS = {
    "RR": "Revenue-Regulations",
    "RMC": "Revenue-Memorandum-Circulars",
    "RMO": "Revenue-Memorandum-Orders",
}

# Sanity-checks that a template_id still points at the category we expect --
# catches BIR silently reassigning IDs rather than misreporting one category's
# issuances as another's.
BIR_CATEGORY_LABELS = {
    "RR": "revenue regulation",
    "RMC": "revenue memorandum circular",
    "RMO": "revenue memorandum order",
}

# Matches abbreviated forms like "RMC No. 61-2026" / "RR No. 3-2026".
_ISSUANCE_RE = re.compile(r"(RR|RMC|RMO)\s*(?:No\.?\s*)?(\d{1,3})-?(\d{4})", re.IGNORECASE)

# Fallback for spelled-out link text, e.g. "Revenue Memorandum Circular No. 61-2026".
_SPELLED_OUT_RE = {
    "RR": re.compile(r"Revenue Regulations?\s*(?:No\.?\s*)?(\d{1,3})-?(\d{4})", re.IGNORECASE),
    "RMC": re.compile(r"Revenue Memorandum Circulars?\s*(?:No\.?\s*)?(\d{1,3})-?(\d{4})", re.IGNORECASE),
    "RMO": re.compile(r"Revenue Memorandum Orders?\s*(?:No\.?\s*)?(\d{1,3})-?(\d{4})", re.IGNORECASE),
}


def _match_issuance(category: str, haystack: str) -> Optional[re.Match]:
    m = _ISSUANCE_RE.search(haystack)
    if m and m.group(1).upper() == category:
        return m
    return _SPELLED_OUT_RE[category].search(haystack)


class BIRAdapter(BaseAdapter):
    """
    Adapter for the Bureau of Internal Revenue (BIR). Reads BIR's own JSON
    data feed rather than scraping rendered HTML (see module docstring above).
    """

    DEFAULT_CATEGORY = "RMC"

    def __init__(self, category: Optional[str] = None, year: Optional[int] = None):
        self.category = (category or self.DEFAULT_CATEGORY).upper()
        self.year = year or datetime.now().year
        self.http_client = ScrapingHttpClient()

    @property
    def regulator_id(self) -> str:
        return "BIR"

    def _build_headers(self) -> dict:
        slug = BIR_REFERER_SLUGS.get(self.category, "")
        referer = f"https://www.bir.gov.ph/{self.year}-{slug}?type=PAGE&to={self.year}-{slug}&label={self.year}"
        return {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "client-website-id": "2",
            "origin": "https://www.bir.gov.ph",
            "referer": referer,
        }

    def fetch_latest_issuances(self) -> List[CandidateIssuance]:
        template_id = BIR_TEMPLATE_IDS.get(self.category)
        if not template_id:
            raise ParsingError(self.regulator_id, f"No known BIR template_id for category '{self.category}'.")

        url = BIR_DATASET_URL.format(template_id=template_id)
        payload = self.http_client.fetch_json(self.regulator_id, url, extra_headers=self._build_headers())

        data = payload.get("data") or []
        if not data:
            raise ParsingError(
                self.regulator_id,
                f"BIR API returned no dataset for {self.category} (template_id {template_id}); "
                "site may have changed -- see module docstring for how to re-discover the ID.",
            )

        entry = data[0]
        label = (entry.get("name") or entry.get("code") or "").lower()
        expected = BIR_CATEGORY_LABELS.get(self.category, "")
        if expected and expected not in label:
            logger.error(
                f"[{self.regulator_id}] template_id {template_id} for {self.category} has label "
                f"'{entry.get('name')}', which doesn't look like {self.category} -- BIR may have "
                "reassigned this ID. Treating this as a fetch failure rather than trusting the data."
            )
            raise ParsingError(
                self.regulator_id,
                f"template_id {template_id} no longer matches category {self.category} "
                f"(got label '{entry.get('name')}').",
            )

        html_content = (entry.get("content") or {}).get("Content", "")
        candidates = self._parse(html_content)
        logger.info(f"[{self.regulator_id}] Extracted {len(candidates)} candidate issuance(s).")
        return candidates

    def _parse(self, html_content: str) -> List[CandidateIssuance]:
        # The API wraps the whole table as one HTML blob (BIR's CMS stores
        # page content as rich text, not per-row structured data) -- this is
        # still HTML we're parsing, but it's HTML handed to us directly by
        # their server, not JavaScript-rendered output we had to fight a
        # browser to see.
        soup = BeautifulSoup(html_content, "html.parser")
        candidates: List[CandidateIssuance] = []
        seen_this_fetch = set()

        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            number_text = clean_text(cells[0].get_text())
            subject_cell = cells[1]
            date_text = clean_text(cells[2].get_text()) if len(cells) > 2 else None

            match = _match_issuance(self.category, number_text) or _match_issuance(
                self.category, subject_cell.get_text(" ", strip=True)
            )
            if not match:
                continue
            number, year = match.group(2), match.group(3)
            number_year = f"{int(number)}-{year}"
            if number_year in seen_this_fetch:
                continue
            seen_this_fetch.add(number_year)

            # Prefer a link explicitly labeled "Full Text"; fall back to the
            # first link in the cell (often "Digest") if that's all there is.
            link_tag = (
                subject_cell.find("a", string=lambda s: s and "full text" in s.lower())
                or subject_cell.find("a", title=lambda t: t and "full text" in t.lower())
                or subject_cell.find("a")
            )
            href = link_tag["href"] if link_tag and link_tag.has_attr("href") else ""
            subject_text = clean_text(subject_cell.get_text(" ", strip=True))

            candidates.append(
                CandidateIssuance(
                    source_regulator=self.regulator_id,
                    source_category=self.category,
                    issuance_identifier=f"{self.category} No. {number_year}",
                    issuance_title=f"{self.category} No. {number_year} - {subject_text[:200]}",
                    source_url=href or f"https://www.bir.gov.ph/{self.year}-{BIR_REFERER_SLUGS.get(self.category, '')}",
                    raw_content_reference=str(row),
                    publication_date=date_text,
                    validation_status="genuine",
                )
            )

        return candidates
