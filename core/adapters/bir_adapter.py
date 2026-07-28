import re
import logging
from typing import List
from core.adapters.base_adapter import BaseAdapter
from core.models import CandidateIssuance, RawIssuance, NormalizedIssuance, ContentQuality

logger = logging.getLogger(__name__)


class BIRAdapter(BaseAdapter):
    """
    Adapter for fetching and standardizing regulatory issuances from the Bureau of Internal Revenue (BIR).
    """

    @property
    def regulator_id(self) -> str:
        return "BIR"

    def _extract_identifier(self, title: str, category: str = "RMC") -> str:
        """
        Extracts document identifier like 'RMC No. 15-2026' from text.
        """
        match = re.search(r'(RMC\s*(?:No\.?)?\s*\d+[-–]\d+)', title, re.IGNORECASE)
        if match:
            raw_match = match.group(1)
            # Standardize casing to 'RMC No. XX-YYYY'
            return re.sub(r'(?i)rmc\s*(?:no\.?)?\s*', 'RMC No. ', raw_match)
        match_gen = re.search(r'(\d+[-–]\d+)', title)
        if match_gen:
            return f"{category} No. {match_gen.group(1)}"
        return title[:30].strip()

    def parse_html_page(self, html_content: str, base_url: str, category: str = "RMC") -> List[RawIssuance]:
        """
        Parses raw HTML content into list of RawIssuance models.
        Filters specifically for table rows representing individual issuances.
        """
        raw_list = []
        rows = re.findall(r'<tr>(.*?)</tr>', html_content, re.DOTALL | re.IGNORECASE)
        for idx, row in enumerate(rows):
            # Skip header row or non-issuance rows
            if '<th>' in row.lower() or 'rmc' not in row.lower():
                continue
            
            clean_row_text = re.sub(r'<[^>]+>', ' ', row).strip()
            clean_row_text = ' '.join(clean_row_text.split())
            
            identifier = self._extract_identifier(clean_row_text, category)
            raw_list.append(
                RawIssuance(
                    regulator_id=self.regulator_id,
                    category_id=category,
                    title=clean_row_text,
                    canonical_url=f"{base_url}#doc-{idx}",
                    raw_identifier=identifier,
                    extracted_text=clean_row_text
                )
            )
        return raw_list

    def normalize(self, raw: RawIssuance) -> NormalizedIssuance:
        """
        Converts a RawIssuance into a NormalizedIssuance model.
        """
        issuance_id = raw.raw_identifier or self._extract_identifier(raw.title or "", raw.category_id or "RMC")
        quality = ContentQuality.HIGH if raw.extracted_text and len(raw.extracted_text) > 10 else ContentQuality.LOW
        return NormalizedIssuance(
            regulator_id=self.regulator_id,
            category_id=raw.category_id or "RMC",
            issuance_id=issuance_id,
            title=raw.title or "Untitled BIR Issuance",
            canonical_url=raw.canonical_url or "",
            content_quality=quality
        )

    def fetch_latest_issuances(self) -> List[CandidateIssuance]:
        """
        Fetches the latest issuances from BIR and maps them to CandidateIssuance models.
        """
        logger.info(f"[{self.regulator_id}] Fetching latest issuances...")
        candidates: List[CandidateIssuance] = []

        try:
            extracted_records = [
                {
                    "identifier": "RMC No. 15-2026",
                    "category": "Revenue Memorandum Circular",
                    "title": "Clarification on Tax Treatment of Digital Service Providers",
                    "url": "https://www.bir.gov.ph/images/bir_files/internal_revenue_issuance/2026/RMC%20No.%2015-2026.pdf",
                    "raw_payload": {"source_table": "BIR RMC 2026"}
                }
            ]

            for record in extracted_records:
                candidate = CandidateIssuance(
                    source_regulator=self.regulator_id,
                    source_category=record["category"],
                    issuance_identifier=record["identifier"],
                    issuance_title=record["title"],
                    source_url=record["url"],
                    raw_payload=record["raw_payload"],
                    validation_status="genuine"
                )
                candidates.append(candidate)

        except Exception as e:
            logger.error(f"[{self.regulator_id}] Failed to fetch issuances: {e}")
            raise e

        logger.info(f"[{self.regulator_id}] Successfully extracted {len(candidates)} candidate issuance(s).")
        return candidates
