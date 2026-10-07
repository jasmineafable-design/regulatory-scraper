"""
Owner reminders: one short email per owner, weekdays, listing their items that
need attention. Read-only against the Sheet; never touches scraper state.

An item appears when it is
  - OVERDUE: open (Applicability Yes/Partially, Status not Closed/Not
    Applicable) and Due Date is before today;
  - DUE SOON: open and due within the next DUE_SOON_DAYS days; or
  - AWAITING ASSESSMENT: Status is "For Assessment" and it was added at least
    ASSESSMENT_GRACE_DAYS days ago (nobody has filled in Applicability yet).

Owners with nothing to chase get no email. The owner is found from the row's
Owner cell: an email address is used as-is; a name is looked up in the
Sources tab's Owner / Owner Email columns. Unknown owners are skipped (and
logged), never guessed.
"""

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Sequence, Tuple

from core.weekly_summary import Item

logger = logging.getLogger(__name__)

DUE_SOON_DAYS = 3
ASSESSMENT_GRACE_DAYS = 3

_EMAIL_RE = re.compile(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+")


def resolve_owner_email(owner: str, directory: Dict[str, str]) -> str:
    owner = (owner or "").strip()
    if not owner:
        return ""
    m = _EMAIL_RE.search(owner)
    if m:
        return m.group(0)
    return directory.get(owner.lower(), "")


@dataclass
class OwnerReminder:
    email: str
    overdue: List[Item] = field(default_factory=list)
    due_soon: List[Item] = field(default_factory=list)
    awaiting: List[Item] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.overdue) + len(self.due_soon) + len(self.awaiting)


def build_reminders(
    items: Sequence[Item], directory: Dict[str, str], today: date
) -> Tuple[List[OwnerReminder], List[str]]:
    """Returns (reminders, unresolved_owner_labels)."""
    by_email: Dict[str, OwnerReminder] = {}
    unresolved: List[str] = []
    soon_limit = today + timedelta(days=DUE_SOON_DAYS)
    grace_cutoff = today - timedelta(days=ASSESSMENT_GRACE_DAYS)

    for it in items:
        bucket = None
        if it.is_open and it.due and it.due < today:
            bucket = "overdue"
        elif it.is_open and it.due and it.due <= soon_limit:
            bucket = "due_soon"
        elif it.status.lower() == "for assessment" and it.added and it.added <= grace_cutoff:
            bucket = "awaiting"
        if not bucket:
            continue

        email = resolve_owner_email(it.owner, directory)
        if not email:
            label = it.owner or "(no owner)"
            if label not in unresolved:
                unresolved.append(label)
            continue
        rem = by_email.setdefault(email, OwnerReminder(email=email))
        getattr(rem, bucket).append(it)

    reminders = sorted(by_email.values(), key=lambda r: r.email)
    return reminders, unresolved


def _e(text: str) -> str:
    return html.escape(text or "")


def _row(it: Item, last_col: str, td: str) -> str:
    label = it.title or it.number
    if it.source.startswith("https://"):
        href = html.escape(it.source.replace(" ", "%20"), quote=True)
        label_html = f'<a href="{href}">{_e(label)}</a>'
    else:
        label_html = _e(label)
    return (
        f"<tr><td {td}><strong>{_e(it.number)}</strong><br/>{label_html}</td>"
        f"<td {td}>{_e(it.priority) or '-'}</td><td {td}>{last_col}</td></tr>"
    )


def build_reminder_email(rem: OwnerReminder, today: date, dashboard_url: str = "") -> Tuple[str, str]:
    subject_bits = []
    if rem.overdue:
        subject_bits.append(f"{len(rem.overdue)} overdue")
    if rem.due_soon:
        subject_bits.append(f"{len(rem.due_soon)} due soon")
    if rem.awaiting:
        subject_bits.append(f"{len(rem.awaiting)} awaiting your assessment")
    subject = "[Reminder] " + ", ".join(subject_bits)

    th = 'style="padding:8px 10px;border:1px solid #dfe3e6;background:#1b2a41;color:#fff;text-align:left;"'
    td = 'style="padding:8px 10px;border:1px solid #dfe3e6;vertical-align:top;"'

    def section(title: str, color: str, items: List[Item], third_header: str, third) -> str:
        if not items:
            return ""
        rows = "".join(_row(i, third(i), td) for i in items)
        return (
            f'<h3 style="color:{color};margin-bottom:4px;">{title} ({len(items)})</h3>'
            f'<table style="border-collapse:collapse;width:100%;"><tr><th {th}>Issuance</th>'
            f"<th {th}>Priority</th><th {th}>{third_header}</th></tr>{rows}</table>"
        )

    body_sections = (
        section("Overdue", "#c0392b", rem.overdue, "Was due",
                lambda i: f'<span style="color:#c0392b;font-weight:bold;">{i.due.strftime("%b %d, %Y")}</span>')
        + section("Due soon", "#d68910", rem.due_soon, "Due",
                  lambda i: i.due.strftime("%b %d, %Y"))
        + section("Awaiting your assessment", "#1b2a41", rem.awaiting, "Added",
                  lambda i: i.added.strftime("%b %d, %Y") if i.added else "-")
    )
    link = (
        f'<p><a href="{html.escape(dashboard_url, quote=True)}">Open the dashboard</a> and go to the '
        f"<strong>Briefings</strong> tab to update your rows.</p>"
        if dashboard_url else "<p>Please update your rows on the dashboard's <strong>Briefings</strong> tab.</p>"
    )
    body = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;line-height:1.5;">
      <h2 style="color:#1b2a41;">Regulatory items that need your attention</h2>
      <p>As of {today.strftime('%A, %B %d, %Y')}. For each item, set <strong>Applicability</strong>,
      <strong>Required Action</strong>, <strong>Due Date</strong> and <strong>Status</strong>
      (use Closed or Not Applicable once it's done, and it drops off this list).</p>
      {body_sections}
      {link}
      <p style="font-size:12px;color:#7f8c8d;">Automated reminder from the Regulatory Scraper. You only receive this when you have items that qualify.</p>
    </body></html>
    """
    return subject, body
