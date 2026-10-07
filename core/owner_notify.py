"""
Owner notification: when new briefings land on the dashboard, email each
issuance's Owner and ask them to record their assessment in the Briefings tab.

The owner's email comes from an optional 'Owner Email' column on the Sources
tab (same (Regulator, Category) rule as the Owner name: exact category row
first, then the regulator-wide row). No email configured -> that briefing is
simply not chased.

Best-effort and fail-open: runs AFTER the briefing email, state commit and
dashboard write, never raises, and a failed owner email can never affect
detection, the briefing, or state.
"""

import html
import logging
from typing import Dict, List, Optional, Sequence, Tuple

from models.issuance import BriefingRecord

logger = logging.getLogger(__name__)

MAX_SUMMARY_CHARS = 220


def _e(text: Optional[str]) -> str:
    return html.escape(text or "")


def _short(text: Optional[str]) -> str:
    t = (text or "").strip()
    if not t or t == "UNAVAILABLE":
        return "Not available"
    return t if len(t) <= MAX_SUMMARY_CHARS else t[: MAX_SUMMARY_CHARS - 1] + "…"


def group_by_owner_email(
    briefings: Sequence[BriefingRecord], emails: Dict[Tuple[str, str], str]
) -> Dict[str, List[BriefingRecord]]:
    groups: Dict[str, List[BriefingRecord]] = {}
    for b in briefings:
        reg = (b.source_regulator or "").strip().upper()
        cat = (b.source_category or "").strip().upper()
        email = emails.get((reg, cat)) or emails.get((reg, ""))
        if email:
            groups.setdefault(email, []).append(b)
    return groups


def build_owner_email(briefings: Sequence[BriefingRecord], dashboard_url: str = "") -> Tuple[str, str]:
    n = len(briefings)
    subject = f"[Action needed] {n} new regulatory issuance{'s' if n != 1 else ''} assigned to you"
    th = 'style="padding:8px 10px;border:1px solid #dfe3e6;background:#1b2a41;color:#fff;text-align:left;"'
    td = 'style="padding:8px 10px;border:1px solid #dfe3e6;vertical-align:top;"'

    rows = ""
    for b in briefings:
        title = (b.issuance_title or "").strip() or b.issuance_identifier
        link = (b.official_source_link or "").strip().replace(" ", "%20")
        title_html = (
            f'<a href="{html.escape(link, quote=True)}">{_e(title)}</a>'
            if link.startswith("https://") else _e(title)
        )
        rows += (
            f"<tr><td {td}><strong>{_e(b.issuance_identifier)}</strong><br/>"
            f'<span style="font-size:12px;color:#7f8c8d;">{_e(b.source_regulator)} / {_e(b.source_category)}</span></td>'
            f"<td {td}>{title_html}</td>"
            f"<td {td}>{_e(_short(b.executive_summary))}</td>"
            f"<td {td}>{_e(b.risk_priority_level) if b.risk_priority_level and b.risk_priority_level != 'UNAVAILABLE' else '-'}</td></tr>"
        )

    link_html = (
        f'<p><a href="{html.escape(dashboard_url, quote=True)}">Open the dashboard</a> and go to the '
        f"<strong>Briefings</strong> tab.</p>" if dashboard_url else
        "<p>Open the dashboard's <strong>Briefings</strong> tab.</p>"
    )
    body = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;line-height:1.5;">
      <h2 style="color:#1b2a41;">New regulatory issuance{'s' if n != 1 else ''} for your assessment</h2>
      <p>You're the assigned owner for the item{'s' if n != 1 else ''} below. Please review
      {'them' if n != 1 else 'it'} and update the team columns on that row:</p>
      <ol>
        <li><strong>Applicability</strong> &ndash; Yes / No / Partially</li>
        <li><strong>Impact/Risk</strong> and <strong>Required Action</strong></li>
        <li><strong>Due Date</strong> and <strong>Status</strong> (e.g. Action Required, In Progress, Closed)</li>
      </ol>
      <table style="border-collapse:collapse;width:100%;"><tr>
        <th {th}>Issuance</th><th {th}>Title</th><th {th}>Summary</th><th {th}>Priority</th></tr>{rows}</table>
      {link_html}
      <p style="font-size:12px;color:#7f8c8d;">Automated message from the Regulatory Scraper. The AI summary is advisory; please confirm against the source.</p>
    </body></html>
    """
    return subject, body


class OwnerNotifier:
    def __init__(self, config_reader, channel):
        self._config_reader = config_reader
        self._channel = channel

    def notify(self, briefings: Sequence[BriefingRecord]) -> int:
        """Emails each owner their new briefings. Returns emails sent. Never raises."""
        sent = 0
        try:
            if not briefings or not hasattr(self._channel, "_send"):
                return 0
            emails = self._config_reader.get_owner_email_matrix()
            if not isinstance(emails, dict) or not emails:
                return 0
            dashboard_url = getattr(self._channel, "dashboard_url", "") or ""
            for email, items in group_by_owner_email(briefings, emails).items():
                try:
                    subject, body = build_owner_email(items, dashboard_url)
                    self._channel._send(subject, body, [email])
                    sent += 1
                except Exception as e:
                    logger.error(f"Owner notification to {email} failed: {e}")
        except Exception as e:
            logger.error(f"Owner notification step skipped: {e}")
        return sent
