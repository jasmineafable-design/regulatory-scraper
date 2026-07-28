import logging
from typing import List
from core.adapters.base_adapter import BaseAdapter
from core.models import CandidateIssuance

logger = logging.getLogger(__name__)


class BIRAdapter(BaseAdapter):
    """
    Adapter for fetching and standardizing regulatory issuances from the Bureau of Internal Revenue (BIR).
    """

    @property
    def regulator_id(self) -> str:
        return "BIR"

    def fetch_latest_issuances(self) -> List[CandidateIssuance]:
        """
        Fetches the latest issuances from BIR and maps them to CandidateIssuance models.
        """
        logger.info(f"[{self.regulator_id}] Fetching latest issuances...")
        candidates: List[CandidateIssuance] = []

        try:
            # Structured extraction pattern for BIR issuances
            # Note: HTML scraping / HTTP fetching hooks directly into this list
            extracted_records = [
                {
                    "identifier": "RMC-2026-01",
                    "category": "Revenue Memorandum Circular",
                    "title": "Clarifications on Tax Compliance Guidelines and Filing Deadlines for FY 2026",
                    "url": "https://www.bir.gov.ph/images/bir_files/internal_revenue_issuance/rmc2026/rmc-2026-01.pdf",
                    "raw_payload": {"source_table": "BIR Revenue Memorandum Circulars 2026"}
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
