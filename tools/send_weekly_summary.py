"""
Sends the weekly management summary email (core/weekly_summary.py).

Reads the Briefings tab and the 'Weekly Summary Recipients' tab from the
configuration Sheet, then emails the summary over the same SMTP settings as the
regular briefings. Read-only against the Sheet; touches no scraper state.

Usage:  python tools/send_weekly_summary.py [--dry-run]
  --dry-run  builds the email and prints who it would go to; sends nothing.
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
from core.sheets_config import SheetsConfigReader  # noqa: E402
from core.weekly_summary import build_summary, items_from_rows, render_html, subject_for  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("weekly_summary")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    reader = SheetsConfigReader()
    ws = reader._worksheet(BRIEFINGS_TAB)
    if not ws:
        logger.error("Could not open the Briefings tab (check SHEET_ID / service account access).")
        return 1

    rows = ws.get_all_values()[1:]  # drop header
    today = datetime.now(ZoneInfo("Asia/Manila")).date()
    summary = build_summary(items_from_rows(rows), today)

    recipients = reader.get_weekly_summary_recipients()
    if not recipients:
        logger.error(
            "No recipients: add a tab named 'Weekly Summary Recipients' to the Sheet "
            "with one email address per row (header 'Email' in A1)."
        )
        return 1

    channel = EmailNotificationChannel()
    html_body = render_html(summary, dashboard_url=channel.dashboard_url)
    subject = subject_for(summary)

    logger.info(
        f"{summary.total_tracked} tracked; {len(summary.new_this_week)} new this week; "
        f"{summary.open_count} open; {summary.overdue} overdue. To: {', '.join(recipients)}"
    )
    if args.dry_run:
        logger.info(f"Dry run -- would send '{subject}'. Nothing sent.")
        return 0

    channel._send(subject, html_body, recipients)
    return 0


if __name__ == "__main__":
    sys.exit(main())
