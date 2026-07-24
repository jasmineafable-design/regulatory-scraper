import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

from core.google_sheets import GoogleSheetsConfigFetcher
from core.logger import setup_logger
from core.models import BusinessEntityConfig, ScraperTargetConfig

load_dotenv()
logger = setup_logger("config")


# Fallback operational configuration used if Google Sheets is unreachable
DEFAULT_SCRAPER_TARGETS = [
    ScraperTargetConfig(
        regulator_id="BIR",
        category_id="RMC",
        category_name="Revenue Memorandum Circulars",
        enabled=True,
        check_interval_hours=24,
    ),
    ScraperTargetConfig(
        regulator_id="IC",
        category_id="CL",
        category_name="Circular Letters",
        enabled=True,
        check_interval_hours=12,
    ),
    ScraperTargetConfig(
        regulator_id="SEC",
        category_id="MC",
        category_name="Memorandum Circulars",
        enabled=True,
        check_interval_hours=24,
    ),
]

# Fallback business entities context
DEFAULT_BUSINESS_ENTITIES = [
    BusinessEntityConfig(
        entity_code="MIGI",
        entity_full_name="Moneeinsure General Insurance",
        primary_focus="Non-Life Insurance",
        key_topics_of_interest=["Capital Requirements", "Reinsurance", "Policy Forms"],
    ),
    BusinessEntityConfig(
        entity_code="MILI",
        entity_full_name="Moneeinsure Life Insurance",
        primary_focus="Life Insurance",
        key_topics_of_interest=["Reserves", "Agent Licensing", "Annuities"],
    ),
    BusinessEntityConfig(
        entity_code="MIBI",
        entity_full_name="Moneeinsure Insurance Brokerage",
        primary_focus="Insurance Brokerage",
        key_topics_of_interest=["Solvency", "Commissions", "Filing Deadlines"],
    ),
]


@dataclass
class SystemConfig:
    """Master application configuration containing operational and business settings."""
    environment: str
    log_level: str
    sheet_csv_url: str
    targets: List[ScraperTargetConfig] = field(default_factory=list)
    entities: List[BusinessEntityConfig] = field(default_factory=list)

    @classmethod
    def load(cls) -> "SystemConfig":
        """Loads complete application settings from Environment Variables and Google Sheets."""
        env = os.getenv("APP_ENV", "development")
        log_lvl = os.getenv("LOG_LEVEL", "INFO")
        sheet_url = os.getenv("CONFIG_GOOGLE_SHEET_CSV_URL", "")

        targets = []
        if sheet_url:
            logger.info("Attempting to load active configuration from Google Sheets...")
            raw_rows = GoogleSheetsConfigFetcher.fetch_csv_as_dicts(sheet_url)
            for row in raw_rows:
                try:
                    target = ScraperTargetConfig(
                        regulator_id=row["regulator_id"].strip().upper(),
                        category_id=row["category_id"].strip().upper(),
                        category_name=row.get("category_name", "").strip(),
                        enabled=row.get("enabled", "true").strip().lower() == "true",
                        check_interval_hours=int(row.get("check_interval_hours", 24)),
                    )
                    targets.append(target)
                except (KeyError, ValueError) as err:
                    logger.warning(f"Skipping invalid Google Sheets row {row}: {err}")

        # Fallback to defaults if Google Sheet fetching fails or yields zero valid targets
        if not targets:
            logger.warning("Using built-in DEFAULT_SCRAPER_TARGETS fallback configuration.")
            targets = DEFAULT_SCRAPER_TARGETS

        entities = DEFAULT_BUSINESS_ENTITIES

        logger.info(
            f"Configuration successfully loaded. Total active scraper targets: {len([t for t in targets if t.enabled])}"
        )

        return cls(
            environment=env,
            log_level=log_lvl,
            sheet_csv_url=sheet_url,
            targets=targets,
            entities=entities,
        )
