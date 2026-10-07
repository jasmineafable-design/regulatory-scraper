"""
Sends owner reminders (core/reminders.py): one email per owner with items that
are overdue, due soon, or still awaiting assessment. Read-only against the
Sheet; touches no scraper state.

Usage:  python tools/send_reminders.py [--dry-run]
  --dry-run  works out who would be emailed and about what; sends nothing.
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dashboard import BRIEFINGS_TAB  # noqa: E402
from core.notify_channels import EmailNotificationChannel  # noqa: E402
from core.reminders import build_reminder_email, build_reminders  # noqa: E402
from core.sheets_config import SheetsConfigReader  # noqa: E402
from core.weekly_summary import items_from_rows  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("reminders")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    reader = SheetsConfigReader()
    ws = reader._worksheet(BRIEFINGS_TAB)
    if not ws:
        logger.error("Could not open the Briefings tab (check SHEET_ID / service account access).")
        return 1

    today = datetime.now(ZoneInfo("Asia/Manila")).date()
    items = items_from_rows(ws.get_all_values()[1:])
    reminders, unresolved = build_reminders(items, reader.get_owner_directory(), today)

    if unresolved:
        logger.warning(
            "Items needing attention whose Owner has no email (add them under Owner + Owner Email "
            f"on the Sources tab, or type an email in the Owner cell): {unresolved}"
        )
    if not reminders:
        logger.info("Nothing to remind anyone about today.")
        return 0

    channel = EmailNotificationChannel()
    failures = 0
    for rem in reminders:
        subject, body = build_reminder_email(rem, today, channel.dashboard_url)
        logger.info(
            f"{rem.email}: {len(rem.overdue)} overdue, {len(rem.due_soon)} due soon, "
            f"{len(rem.awaiting)} awaiting assessment."
        )
        if args.dry_run:
            continue
        try:
            channel._send(subject, body, [rem.email])
        except Exception as e:
            failures += 1
            logger.error(f"Reminder to {rem.email} failed: {e}")

    if args.dry_run:
        logger.info("Dry run -- nothing sent.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
