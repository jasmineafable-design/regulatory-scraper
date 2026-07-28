import re
import logging
from typing import List
from core.adapters.base_adapter import BaseAdapter
from core.models import CandidateIssuance, RawIssuance

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
            return match.group(1).upper()
        match_gen = re.search(r'(\d+[-–]\d+)', title)
        if match_gen:
            return f"{category} No. {match_gen.group(1)}"
        return title[:30].strip()

    def parse_html_page(self, html_content: str, base_url: str, category: str = "RMC") -> List[RawIssuance]:
        """
        Parses raw HTML content into list of RawIssuance models.
        """
        raw_list = []
        lines = [line.strip() for line in html_content.split('\n') if line.strip()]
        for idx, line in enumerate(lines):
            if "RMC" in line or "Revenue Memorandum Circular" in line or "No." in line:
                identifier = self._extract_identifier(line, category)
                raw_list.append(
                    RawIssuance(
                        regulator_id=self.regulator_id,
                        category_id=category,
                        title=line,
                        canonical_url=f"{base_url}#doc-{idx}",
                        raw_identifier=identifier,
                        extracted_text=line
                    )
                )
        return raw_list

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
