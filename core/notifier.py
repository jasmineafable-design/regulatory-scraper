import json
from typing import List
import requests

from core.logger import setup_logger
from core.models import CandidateIssuance

logger = setup_logger("notifier")


class NotificationDispatcher:
    """Dispatches notifications for new regulatory issuances."""

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url

    def dispatch(self, discoveries: List[CandidateIssuance]) -> bool:
        """Sends a structured payload of new discoveries to configured endpoints."""
        if not discoveries:
            logger.info("No discoveries to dispatch.")
            return True

        if not self.webhook_url:
            logger.warning("No webhook URL configured. Logging discoveries locally only.")
            for item in discoveries:
                logger.info(f"[DISPATCH ALERT] {item.regulator_id} | {item.issuance_identifier} | {item.title}")
            return True

        payload = {
            "summary": f"🚨 Regulatory Intelligence Alert: {len(discoveries)} New Issuance(s) Discovered",
            "issuances": [
                {
                    "regulator": item.regulator_id,
                    "identifier": item.issuance_identifier,
                    "title": item.title,
                    "document_url": item.document_url,
                }
                for item in discoveries
            ],
        }

        try:
            response = requests.post(
                self.webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            logger.info(f"Successfully dispatched notification for {len(discoveries)} items.")
            return True
        except Exception as e:
            logger.error(f"Failed to dispatch notification webhook: {e}", exc_info=True)
            return False
