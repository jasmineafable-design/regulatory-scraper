import logging
from typing import Optional
from core.models import BriefingRecord

logger = logging.getLogger(__name__)


def format_briefing_message(briefing: BriefingRecord) -> str:
    """
    Formats a BriefingRecord into a standardized plaintext/markdown message for delivery.
    """
    lines = [
        f"🚨 **NEW REGULATORY ISSUANCE: {briefing.source_regulator}**",
        f"**Identifier:** {briefing.issuance_identifier}",
        f"**Category:** {briefing.source_category}",
        f"**Title:** {briefing.issuance_title}",
        f"**Official Link:** {briefing.official_source_link}",
        f"**Completeness:** {briefing.completeness_status.upper()}",
    ]

    if briefing.executive_summary:
        lines.append(f"\n**Summary:**\n{briefing.executive_summary}")
    
    if briefing.risk_priority_level:
        lines.append(f"**Risk Priority:** {briefing.risk_priority_level}")
        
    if briefing.suggested_action:
        lines.append(f"**Suggested Action:** {briefing.suggested_action}")

    return "\n".join(lines)


def send_notification(briefing: BriefingRecord) -> bool:
    """
    Dispatches a briefing notification.
    
    Returns True if delivery succeeded, or False if delivery failed.
    State commit MUST only proceed if this returns True.
    """
    message = format_briefing_message(briefing)
    
    try:
        # Stub / local console output for deterministic testing during Phase 1
        print("=" * 60)
        print("[NOTIFY DISPATCH]")
        print(message)
        print("=" * 60)
        
        # Real adapter calls (e.g., Telegram / Email / Google Sheets) hook in here
        return True
    except Exception as e:
        logger.error(f"Failed to send notification for {briefing.issuance_identifier}: {e}")
        return False
