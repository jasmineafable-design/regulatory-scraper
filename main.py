from core.adapters.bir_adapter import BIRAdapter
from core.adapters.ic_adapter import ICAdapter
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

    # 3. Active Adapters to Execute
    adapters = [
        BIRAdapter(),
        ICAdapter(),
    ]

    total_new_discoveries = 0

    for adapter in adapters:
        logger.info(f"--- Running Adapter: {adapter.regulator_id} ---")
        
        try:
            # Standardized parameterless invocation across all adapters
            candidates = adapter.fetch_latest_issuances()
            logger.info(f"Fetched {len(candidates)} candidate items from {adapter.regulator_id}")

            adapter_new_count = 0
            for candidate in candidates:
                identifier = candidate.issuance_identifier

                if not state_mgr.is_seen(identifier):
                    logger.info(f"[NEW DISCOVERY] {identifier} - {candidate.title[:60]}...")
                    
                    # Record the candidate into the state ledger
                    state_mgr.record_issuance(candidate, status="PROCESSED")
                    adapter_new_count += 1
                else:
                    logger.debug(f"[SEEN] Skipping {identifier}")

            total_new_discoveries += adapter_new_count
            logger.info(f"Completed {adapter.regulator_id}: {adapter_new_count} new discoveries.")

        except Exception as e:
            logger.error(f"Error executing adapter {adapter.regulator_id}: {e}", exc_info=True)

    # 4. Commit State Persistence
    if total_new_discoveries > 0:
        state_mgr.commit()
        logger.info(f"Committed {total_new_discoveries} new issuance records to state ledger.")
    else:
        logger.info("No new unseen regulatory issuances found during this run.")

    logger.info("Regulatory Scraper System execution completed successfully.")


if __name__ == "__main__":
    main()
