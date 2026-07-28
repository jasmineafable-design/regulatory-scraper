import json
from typing import List
import requests

from core.logger import setup_logger
from core.models import CandidateIssuance

logger = setup_logger("notifier")


class NotificationDispatcher:
    """Dispatches regulatory alerts and daily monitoring briefings."""

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url

    def dispatch_alert(self, discoveries: List[CandidateIssuance]) -> bool:
        """Sends an immediate Regulatory Briefing when new issuances are found."""
        if not discoveries:
            logger.info("No discoveries to alert.")
            return True

        if not self.webhook_url:
            logger.warning("No webhook URL configured. Logging alert locally.")
            for item in discoveries:
                logger.info(f"[DISPATCH ALERT] {item.source_regulator} | {item.issuance_identifier} | {item.issuance_title}")
            return True

        payload = {
            "summary": f"🚨 Regulatory Briefing: {len(discoveries)} New Issuance(s) Discovered",
            "type": "REGULATORY_BRIEFING",
            "issuances": [
                {
                    "regulator": item.source_regulator,
                    "category": item.source_category,
                    "identifier": item.issuance_identifier,
                    "title": item.issuance_title,
                    "document_url": item.source_url,
                }
                for item in discoveries
            ],
        }

        return self._send_webhook(payload)

    def dispatch_daily_report(self, status: str = "ALL_CLEAR", count: int = 0) -> bool:
        """Sends the Daily Monitoring Report during the opening run when no items are found."""
        if not self.webhook_url:
            logger.info(f"[DAILY MONITORING REPORT] Status: {status} | New Issuances: {count}")
            return True

        payload = {
            "summary": "📋 Daily Monitoring Report: Opening Run Complete",
            "type": "DAILY_MONITORING_REPORT",
            "status": status,
            "message": "The system initialized the business day monitoring cycle. All monitored regulators (BIR, IC, SEC) are clear with no new issuances pending.",
            "new_issuances_count": count,
        }

        return self._send_webhook(payload)

    def _send_webhook(self, payload: dict) -> bool:
        """Helper to post payload to configured webhook URL."""
        try:
            response = requests.post(
                self.webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            logger.info(f"Successfully dispatched {payload.get('type')} webhook.")
            return True
        except Exception as e:
            logger.error(f"Failed to dispatch webhook: {e}", exc_info=True)
            return False
