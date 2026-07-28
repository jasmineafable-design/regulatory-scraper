# File: main.py

import logging
from src.storage.state_store import StateManager
from src.pipeline.orchestrator import RegulatoryPipeline
from src.adapters.sec import SECAdapter
from src.notifier.email_notifier import EmailNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")


def main():
    logger.info("Initializing Regulatory Scraper Pipeline...")
    
    # Initialize components
    state_store = StateManager(state_file_path="data/processed_state.json")
    notifier = EmailNotifier()
    
    adapters = [
        SECAdapter(),
        # Add BIRAdapter(), ICAdapter(), etc.
    ]
    
    # Pass notifier to orchestrator
    pipeline = RegulatoryPipeline(
        adapters=adapters, 
        state_store=state_store, 
        notifier=notifier
    )
    
    logger.info("Starting pipeline execution run...")
    results = pipeline.run(is_morning_check=False)
    logger.info(f"Pipeline execution completed: {results}")


if __name__ == "__main__":
    main()
