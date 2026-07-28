import logging
import datetime
from typing import List, Dict, Any
from src.storage.state_store import StateStore

logger = logging.getLogger(__name__)

class RegulatoryPipeline:
    """
    Orchestrates the 7-step critical path pipeline for regulatory intelligence.
    """

    def __init__(self, adapters: List[Any], state_store: StateStore, notifier: Any = None):
        self.adapters = adapters
        self.state_store = state_store
        self.notifier = notifier

    def run(self, is_morning_check: bool = False) -> Dict[str, Any]:
        """
        Executes the full pipeline run across all configured adapters.
        """
        raw_items: List[Dict[str, Any]] = []
        new_items: List[Dict[str, Any]] = []

        # Step 1 & 2: Fetch & Validate
        for adapter in self.adapters:
            try:
                fetched = adapter.fetch()
                raw_items.extend(fetched)
            except Exception as e:
                logger.error(f"Error fetching from adapter {adapter.__class__.__name__}: {str(e)}")
                # Fail-loud architecture principle
                raise e

        # Step 3: Detect (Filter non-processed items)
        for item in raw_items:
            item_id = item.get("url") or item.get("title")
            if item_id and not self.state_store.is_processed(item_id):
                new_items.append(item)

        # Step 4, 5 & 6: Assess, Compose & Notify Branching
        if new_items:
            logger.info(f"Detected {len(new_items)} new issuance(s). Triggering immediate briefing.")
            if self.notifier:
                self.notifier.send_immediate_briefing(new_items)
            
            # Step 7: Commit State
            for item in new_items:
                item_id = item.get("url") or item.get("title")
                self.state_store.commit(item_id)

        elif is_morning_check:
            logger.info("No new issuances found during morning run. Sending Daily Monitoring Report.")
            if self.notifier:
                self.notifier.send_daily_monitoring_report()

        else:
            logger.info("No new issuances detected during regular run. Remaining silent.")

        return {
            "total_fetched": len(raw_items),
            "new_processed": len(new_items),
            "status": "SUCCESS"
        }
