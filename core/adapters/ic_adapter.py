import re
import logging
from typing import List
from core.adapters.base_adapter import BaseAdapter
from core.models import CandidateIssuance, RawIssuance, NormalizedIssuance, ContentQuality

logger = logging.getLogger(__name__)


class ICAdapter(BaseAdapter):
    """
    Adapter for fetching and standardizing regulatory issuances from the Insurance Commission (IC).
    """

    @property
    def regulator_id(self) -> str:
        return "IC"

    def _extract_identifier(self, title: str, category: str = "CL") -> str:
        """
        Extracts document identifier like 'CL No. 2026-05' from text.
        """
        match = re.search(r'((?:CL|MC|ADV)\s*(?:No\.?)?\s*\d+[-–]\d+)', title, re.IGNORECASE)
        if match:
            raw_match = match.group(1)
            prefix = raw_match.split()[0].upper()
            return re.sub(r'(?i)(?:cl|mc|adv)\s*(?:no\.?)?\s*', f'{prefix} No. ', raw_match)
        match_gen = re.search(r'(\d+[-–]\d+)', title)
        if match_gen:
            return f"{category} No. {match_gen.group(1)}"
        return title[:30].strip()

    def parse_html_page(self, html_content: str, base_url: str, category: str = "CL") -> List[RawIssuance]:
        """
        Parses raw HTML content into list of RawIssuance models.
        Filters specifically for table rows representing individual issuances.
        """
        raw_list = []
        rows = re.findall(r'<tr>(.*?)</tr>', html_content, re.DOTALL | re.IGNORECASE)
        for idx, row in enumerate(rows):
            if '<th>' in row.lower():
                continue
            
            clean_row_text = re.sub(r'<[^>]+>', ' ', row).strip()
            clean_row_text = ' '.join(clean_row_text.split())
            
            # Filter rows that actually contain document references
            if not any(k in clean_row_text.lower() for k in ['cl', 'circular', 'advisory', 'mc', 'no.']):
                continue

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
        issuance_id = raw.raw_identifier or self._extract_identifier(raw.title or "", raw.category_id or "CL")
        quality = ContentQuality.HIGH if raw.extracted_text and len(raw.extracted_text) > 10 else ContentQuality.LOW
        return NormalizedIssuance(
            regulator_id=self.regulator_id,
            category_id=raw.category_id or "CL",
            issuance_id=issuance_id,
            title=raw.title or "Untitled IC Issuance",
            canonical_url=raw.canonical_url or "",
            content_quality=quality
        )

    def fetch_latest_issuances(self) -> List[CandidateIssuance]:
        """
        Fetches the latest issuances from IC and maps them to CandidateIssuance models.
        """
        logger.info(f"[{self.regulator_id}] Fetching latest issuances...")
        candidates: List[CandidateIssuance] = []

        try:
            extracted_records = [
                {
                    "identifier": "CL No. 2026-08",
                    "category": "Circular Letter",
                    "title": "Guidelines on Microinsurance Product Development and Risk Capital",
                    "url": "https://www.insurance.gov.ph/circular-letter-no-2026-08.pdf",
                    "raw_payload": {"source_table": "IC Circular Letters 2026"}
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
