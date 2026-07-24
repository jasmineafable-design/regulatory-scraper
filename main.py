from core.adapters.bir_adapter import BIRAdapter
from core.config import SystemConfig
from core.logger import setup_logger
from core.state import StateManager

logger = setup_logger("main")


def main() -> None:
    """Primary system execution entry point."""
    logger.info("Initializing Regulatory Scraper System...")

    # 1. Load System Configuration
    config = SystemConfig.load()
    logger.info(f"System Environment: {config.environment}")

    # 2. Initialize State Manager Memory
    state_mgr = StateManager()

    # 3. Initialize BIR Adapter
    bir_adapter = BIRAdapter()
    logger.info(f"Active Regulator Adapter: {bir_adapter.regulator_id}")

    # 4. Process BIR Categories
    category_id = "RMC"
    bir_config = {
        "target_url": "https://www.bir.gov.ph/revenue-issuances-details"
    }

    raw_list = bir_adapter.fetch_latest_issuances(category_id, bir_config)
    logger.info(f"Fetched {len(raw_list)} raw items from BIR {category_id}")

    new_discovered_count = 0
    for raw_item in raw_list:
        normalized = bir_adapter.normalize(raw_item)

        if not state_mgr.is_seen(normalized.issuance_id):
            logger.info(f"[NEW DISCOVERY] {normalized.issuance_id} - {normalized.title[:60]}...")
            state_mgr.record_issuance(normalized, status="PROCESSED")
            new_discovered_count += 1
        else:
            logger.debug(f"[SEEN] Skipping {normalized.issuance_id}")

    if new_discovered_count > 0:
        state_mgr.commit()
        logger.info(f"Committed {new_discovered_count} new issuance records to state file.")
    else:
        logger.info("No new unseen BIR issuances found during this run.")

    logger.info("Phase 5 BIR Adapter execution completed successfully.")


if __name__ == "__main__":
    main()
