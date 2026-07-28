import os
import sys
import logging
import argparse
from typing import List

from src.config.sheets_config import SheetsConfigReader
from src.storage.state_store import StateStore
from src.adapters.bir import BIRAdapter
from src.adapters.ic import ICAdapter
from src.adapters.sec import SECAdapter
from src.pipeline.orchestrator import RegulatoryPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("RegulatoryIntelligence")

def main():
    parser = argparse.ArgumentParser(description="Regulatory Intelligence Automated Scraper")
    parser.add_argument("--morning-check", action="store_true", help="Flag indicating morning check run for daily summary")
    args = parser.parse_args()

    logger.info("Initializing Regulatory Intelligence Pipeline...")

    # Load configuration
    sheet_id = os.getenv("SPREADSHEET_ID")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    
    # Initialize State Store
    state_store = StateStore()

    # Load Adapters Dynamically based on Operational Config
    adapters = []
    if os.path.exists(creds_path) and sheet_id:
        try:
            config_reader = SheetsConfigReader(service_account_json=creds_path, spreadsheet_id=sheet_id)
            ops_config = config_reader.get_operational_config()

            if str(ops_config.get("BIR_ENABLED", "TRUE")).upper() == "TRUE":
                adapters.append(BIRAdapter())
            if str(ops_config.get("IC_ENABLED", "TRUE")).upper() == "TRUE":
                adapters.append(ICAdapter())
            if str(ops_config.get("SEC_ENABLED", "TRUE")).upper() == "TRUE":
                adapters.append(SECAdapter())
        except Exception as e:
            logger.warning(f"Failed to load Sheets config; falling back to default adapters: {str(e)}")
            adapters = [BIRAdapter(), ICAdapter(), SECAdapter()]
    else:
        logger.info("Google Sheets credentials not provided. Defaulting to all active adapters.")
        adapters = [BIRAdapter(), ICAdapter(), SECAdapter()]

    # Execute Orchestrator
    orchestrator = RegulatoryPipeline(
        adapters=adapters,
        state_store=state_store,
        notifier=None  # Wire your Email/Slack/Teams notifier instance here
    )

    results = orchestrator.run(is_morning_check=args.morning_check)
    logger.info(f"Pipeline Run Completed: {results}")

if __name__ == "__main__":
    main()
