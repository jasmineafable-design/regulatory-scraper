import argparse
import logging
import os
import sys

from core.storage.state_manager import StateManager
from core.adapters.sec_adapter import SECAdapter
# Import your other adapters here if needed
# from core.adapters.bir_adapter import BIRAdapter
# from core.adapters.ic_adapter import ICAdapter

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("main")

def main():
    parser = argparse.ArgumentParser(description="Regulatory Intelligence Automated Scraper")
    parser.add_argument("--morning-check", action="store_true", help="Flag indicating morning check run for daily summary")
    args = parser.parse_args()

    logger.info(f"Starting Regulatory Intelligence cycle (Opening Run: {args.morning_check})...")

    state_manager = StateManager()
    
    # Initialize active adapters
    adapters = [SECAdapter()]

    new_issuances = []

    for adapter in adapters:
        regulator_name = getattr(adapter, "source_regulator", adapter.__class__.__name__)
        logger.info(f"Executing adapter for {regulator_name}...")
        try:
            candidates = adapter.fetch_latest_issuances()
            for candidate in candidates:
                if not state_manager.is_seen(candidate.source_regulator, candidate.issuance_identifier):
                    new_issuances.append(candidate)
                    state_manager.mark_seen(candidate.source_regulator, candidate.issuance_identifier)
        except Exception as e:
            logger.error(f"Adapter execution failed for {regulator_name}: {e}", exc_info=True)

    if new_issuances:
        logger.info(f"Discovered {len(new_issuances)} new issuance(s)!")
        # Trigger notification logic here once notifier is wired
    else:
        logger.info("Polling run complete. No new issuances discovered. Remaining silent.")

    logger.info("Cycle complete.")

if __name__ == "__main__":
    main()
