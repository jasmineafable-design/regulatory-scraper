import argparse
import os
import sys
from typing import List

from core.adapters.bir_adapter import BIRAdapter
from core.adapters.ic_adapter import ICAdapter
from core.adapters.sec_adapter import SECAdapter
from core.config import settings
from core.logger import setup_logger
from core.models import CandidateIssuance
from core.notifier import NotificationDispatcher
from core.state import StateManager

logger = setup_logger("main")


def parse_args():
    parser = argparse.ArgumentParser(description="Regulatory Intelligence Orchestrator")
    parser.add_argument(
        "--is-opening-run",
        action="store_true",
        help="Designates this execution as the business day opening run (10:00 AM). Emits Daily Monitoring Report if clear.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    logger.info(f"Starting Regulatory Intelligence cycle (Opening Run: {args.is_opening_run})...")

    # Ensure state directory exists before initializing StateManager
    state_dir = os.path.dirname(settings.STATE_FILE_PATH)
    if state_dir and not os.path.exists(state_dir):
        os.makedirs(state_dir, exist_ok=True)

    state_manager = StateManager(db_path=settings.STATE_FILE_PATH)
    dispatcher = NotificationDispatcher(webhook_url=settings.SLACK_WEBHOOK_URL)

    adapters = [
        BIRAdapter(),
        ICAdapter(),
        SECAdapter(),
    ]

    new_discoveries: List[CandidateIssuance] = []

    for adapter in adapters:
        logger.info(f"Executing adapter for {adapter.regulator_id}...")
        try:
            candidates = adapter.fetch_latest_issuances()
            for candidate in candidates:
                if not state_manager.is_seen(candidate.source_regulator, candidate.issuance_identifier):
                    new_discoveries.append(candidate)
                    state_manager.mark_seen(candidate.source_regulator, candidate.issuance_identifier)
        except Exception as e:
            logger.error(f"Adapter execution failed for {adapter.regulator_id}: {e}", exc_info=True)

    if new_discoveries:
        logger.info(f"Found {len(new_discoveries)} new issuance(s). Dispatching Regulatory Briefing...")
        dispatcher.dispatch_alert(new_discoveries)
        state_manager.save_state()
    elif args.is_opening_run:
        logger.info("Opening run clear. Dispatching Daily Monitoring Report...")
        dispatcher.dispatch_daily_report(status="ALL_CLEAR", count=0)
    else:
        logger.info("Polling run complete. No new issuances discovered. Remaining silent.")

    logger.info("Cycle complete.")


if __name__ == "__main__":
    main()
