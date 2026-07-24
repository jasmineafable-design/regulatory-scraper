from core.config import SystemConfig
from core.logger import setup_logger
from core.models import ContentQuality, NormalizedIssuance
from core.state import StateManager

logger = setup_logger("main")


def main() -> None:
    """Primary system entry point."""
    logger.info("Initializing Regulatory Scraper System...")

    # 1. Load System Configuration
    config = SystemConfig.load()
    logger.info(f"System Environment: {config.environment}")

    # 2. Initialize State Manager Memory
    state_mgr = StateManager()

    # 3. Demonstrate Deduplication Check
    sample_issuance = NormalizedIssuance(
        issuance_id="BIR_RMC_15-2026",
        regulator_id="BIR",
        category_id="RMC",
        title="Revenue Memorandum Circular No. 15-2026",
        canonical_url="https://www.bir.gov.ph/rmc_15_2026.pdf",
        content_quality=ContentQuality.VALID,
    )

    if not state_mgr.is_seen(sample_issuance.issuance_id):
        logger.info(f"New issuance discovered: {sample_issuance.issuance_id}. Recording to state...")
        state_mgr.record_issuance(sample_issuance, status="PROCESSED")
        state_mgr.commit()
    else:
        logger.info(f"Issuance {sample_issuance.issuance_id} has already been seen and processed. Skipping.")

    logger.info("Phase 3 State Management Subsystem active and operational.")


if __name__ == "__main__":
    main()
