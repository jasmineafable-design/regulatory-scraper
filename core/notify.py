import logging
from typing import List, Protocol
from models.issuance import BriefingRecord

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    """Abstract protocol for sending notifications."""

    def send_regulatory_briefing(self, briefing: BriefingRecord) -> bool:
        ...

    def send_daily_monitoring_report(self, run_time_info: str) -> bool:
        ...


class ConsoleNotificationChannel:
    """Mock/Fallback console channel for testing and standard output."""

    def send_regulatory_briefing(self, briefing: BriefingRecord) -> bool:
        print(f"\n--- [REGULATORY BRIEFING] ---")
        print(f"Agency: {briefing.source_regulator} ({briefing.source_category})")
        print(f"ID: {briefing.issuance_identifier}")
        print(f"Title: {briefing.issuance_title}")
        print(f"Official Link: {briefing.official_source_link}")
        print(f"Executive Summary: {briefing.executive_summary}")
        print(f"Completeness: {briefing.completeness_status}")
        print("-----------------------------\n")
        return True

    def send_daily_monitoring_report(self, run_time_info: str) -> bool:
        print(f"\n--- [DAILY MONITORING REPORT] ---")
        print(f"Status: No new issuances detected during opening check.")
        print(f"Details: {run_time_info}")
        print("---------------------------------\n")
        return True


class NotificationDispatcher:
    """Implements §3.7 notification branching rules."""

    def __init__(self, channel: NotificationChannel):
        self.channel = channel

    def dispatch(
        self,
        briefings: List[BriefingRecord],
        is_opening_check: bool,
        check_timestamp_info: str = "Standard Execution",
    ) -> List[BriefingRecord]:
        """Applies §3.7 branching rules:
        
        - Any check finds items -> Send Regulatory Briefing for each item.
        - Opening check finds 0 items -> Send Daily Monitoring Report.
        - Recurring check finds 0 items -> Send nothing.
        
        Returns the list of BriefingRecords that were successfully notified.
        """
        successful_briefings: List[BriefingRecord] = []

        if briefings:
            # Send Regulatory Briefing for each new issuance
            for briefing in briefings:
                success = self.channel.send_regulatory_briefing(briefing)
                if success:
                    successful_briefings.append(briefing)
                else:
                    logger.error(
                        f"Failed to dispatch briefing for {briefing.issuance_identifier}"
                    )
        else:
            # 0 new issuances found
            if is_opening_check:
                logger.info("Opening check found 0 new items. Sending Daily Monitoring Report.")
                self.channel.send_daily_monitoring_report(check_timestamp_info)
            else:
                logger.info("Recurring check found 0 new items. No notification sent.")

        return successful_briefings
