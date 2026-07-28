# File: main.py

import logging
import sys

# Change from core.storage.state_manager to src.storage.state_store
from src.storage.state_store import StateManager  # or StateStore
from src.pipeline.orchestrator import RegulatoryPipeline
from src.adapters.sec import SECAdapter
# Import any other adapters or modules here (e.g., BIR, IC, Notifier)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")


def main():
    logger.info("Initializing Regulatory Scraper Pipeline...")
    
    # Initialize State Store
    state_store = StateManager(state_file_path="data/processed_state.json")
    
    # Initialize Adapters
    adapters = [
        SECAdapter(),
        # Add BIRAdapter(), ICAdapter(), etc.
    ]
    
    # Initialize Pipeline
    pipeline = RegulatoryPipeline(adapters=adapters, state_store=state_store)
    
    # Run execution loop
    logger.info("Starting pipeline execution run...")
    results = pipeline.run(is_morning_check=False)
    
    logger.info(f"Pipeline completed successfully. Processed results: {results}")


if __name__ == "__main__":
    main()
