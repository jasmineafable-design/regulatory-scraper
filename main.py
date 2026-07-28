from core.adapters.bir_adapter import BIRAdapter
from core.adapters.ic_adapter import ICAdapter
from core.adapters.sec_adapter import SECAdapter  # <--- Added
from core.config import SystemConfig
from core.logger import setup_logger
from core.state import StateManager

logger = setup_logger("main")


def main() -> None:
    """Primary system execution entry point."""
    logger.info("Initializing Regulatory Scraper System...")

    config = SystemConfig.load()
    logger.info(f"System Environment: {config.environment}")

    state_mgr = StateManager()

    # Active Adapters Array
    adapters = [
        BIRAdapter(),
        ICAdapter(),
        SECAdapter(),  # <--- Added
    ]

    total_new_discoveries = 0

    for adapter in adapters:
        logger.info(f"--- Running Adapter: {adapter.regulator_id} ---")
        
        try:
            candidates = adapter.fetch_latest_issuances()
            logger.info(f"Fetched {len(candidates)} candidate items from {adapter.regulator_id}")

            adapter_new_count = 0
            for candidate in candidates:
                identifier = candidate.issuance_identifier

                if not state_mgr.is_seen(identifier):
                    logger.info(f"[NEW DISCOVERY] {identifier} - {candidate.title[:60]}...")
                    state_mgr.record_issuance(candidate, status="PROCESSED")
                    adapter_new_count += 1
                else:
                    logger.debug(f"[SEEN] Skipping {identifier}")

            total_new_discoveries += adapter_new_count
            logger.info(f"Completed {adapter.regulator_id}: {adapter_new_count} new discoveries.")

        except Exception as e:
            logger.error(f"Error executing adapter {adapter.regulator_id}: {e}", exc_info=True)

    if total_new_discoveries > 0:
        state_mgr.commit()
        logger.info(f"Committed {total_new_discoveries} new issuance records to state ledger.")
    else:
        logger.info("No new unseen regulatory issuances found during this run.")

    logger.info("Regulatory Scraper System execution completed successfully.")


if __name__ == "__main__":
    main()
