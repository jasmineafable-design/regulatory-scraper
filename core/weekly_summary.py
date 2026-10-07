"""
Weekly management summary email.

Reads the dashboard's "Briefings" tab (the same data the Dashboard cards use)
and emails a short, plain summary: what's new this week, how many items are
waiting / high-risk / overdue / due soon, and the top items needing action.

Definitions deliberately mirror the Dashboard (core/dashboard.py):
  Open       = Applicability is Yes/Partially AND Status is not Closed/Not Applicable
  For Assessment = Status "For Assessment"
  High-Risk Open = Open AND Review Priority HIGH
  Overdue    = Open AND Due Date before today
  Due Soon   = Open AND Due Date within the next 30 days

Read-only against the Sheet; never changes state or notification behaviour.
"""

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Briefings tab columns (0-based), same layout as core/dashboard.py.
C_DATE, C_REG, C_TYPE, C_NO, C_TITLE, C_PRIORITY = 0, 1, 2, 3, 4, 5
C_SOURCE = 12
C_APPLIC, C_ACTION, C_OWNER, C_DUE, C_STATUS = 14, 16, 17, 18, 19

CLOSED_STATUSES = {"closed", "not applicable"}
DUE_SOON_DAYS = 30
MAX_ACTION_ROWS = 10
MAX_NEW_ROWS = 15

_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y", "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%Y/%m/%d")


def parse_date(value: str) -> Optional[date]:
    s = (value or "").strip()
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _cell(row: Sequence[str], idx: int) -> str:
    return str(row[idx]).strip() if idx < len(row) and row[idx] is not None else ""


@dataclass
class Item:
    added: Optional[date]
    regulator: str
    type: str
    number: str
    title: str
    priority: str
    source: str
    applicability: str
    action: str
    owner: str
    due: Optional[date]
    status: str

    @property
    def is_open(self) -> bool:
        return (
            self.applicability.lower() in ("yes", "partially")
            and self.status.lower() not in CLOSED_STATUSES
        )

    @property
    def is_high(self) -> bool:
        return self.priority.upper() == "HIGH"


@dataclass
class Summary:
    as_of: date
    new_this_week: List[Item] = field(default_factory=list)
    for_assessment: int = 0
    open_count: int = 0
    high_open: int = 0
    overdue: int = 0
    due_soon: int = 0
    action_rows: List[Item] = field(default_factory=list)
    by_regulator: Dict[str, int] = field(default_factory=dict)
    total_tracked: int = 0


def items_from_rows(rows: Sequence[Sequence[str]]) -> List[Item]:
    """rows = Briefings values WITHOUT the header row."""
    items: List[Item] = []
    for r in rows:
        if not _cell(r, C_REG) and not _cell(r, C_NO):
            continue  # blank spacer row
        if _cell(r, C_REG).upper() == "DEMO":
            continue
        items.append(Item(
            added=parse_date(_cell(r, C_DATE)),
            regulator=_cell(r, C_REG),
            type=_cell(r, C_TYPE),
            number=_cell(r, C_NO),
            title=_cell(r, C_TITLE),
            priority=_cell(r, C_PRIORITY),
            source=_cell(r, C_SOURCE),
            applicability=_cell(r, C_APPLIC),
            action=_cell(r, C_ACTION),
            owner=_cell(r, C_OWNER),
            due=parse_date(_cell(r, C_DUE)),
            status=_cell(r, C_STATUS),
        ))
    return items


def build_summary(items: Sequence[Item], today: date) -> Summary:
    s = Summary(as_of=today, total_tracked=len(items))
    week_ago = today - timedelta(days=7)
    soon_limit = today + timedelta(days=DUE_SOON_DAYS)

    for it in items:
        if it.added and it.added > week_ago:
            s.new_this_week.append(it)
            s.by_regulator[it.regulator.upper()] = s.by_regulator.get(it.regulator.upper(), 0) + 1
        if it.status.lower() == "for assessment":
            s.for_assessment += 1
        if it.is_open:
            s.open_count += 1
            if it.is_high:
                s.high_open += 1
            if it.due and it.due < today:
                s.overdue += 1
            elif it.due and it.due <= soon_limit:
                s.due_soon += 1

    far = date.max
    open_items = [i for i in items if i.is_open]
    # Overdue first, then High priority, then earliest due date, then newest.
    open_items.sort(key=lambda i: (
        0 if (i.due and i.due < today) else 1,
        0 if i.is_high else 1,
        i.due or far,
        -(i.added.toordinal() if i.added else 0),
    ))
    s.action_rows = open_items[:MAX_ACTION_ROWS]
    s.new_this_week.sort(key=lambda i: (0 if i.is_high else 1, i.regulator, i.number))
    return s


# -- Rendering --------------------------------------------------------------

_BADGE = {
    "red": "#c0392b", "amber": "#d68910", "green": "#1e8449", "grey": "#7f8c8d", "navy": "#1b2a41",
}


def _e(text: str) -> str:
    return html.escape(text or "")


def _card(label: str, value: int, color: str) -> str:
    return (
        f'<td style="padding:10px 14px;text-align:center;border:1px solid #dfe3e6;">'
        f'<div style="font-size:26px;font-weight:bold;color:{_BADGE[color]};">{value}</div>'
        f'<div style="font-size:12px;color:#7f8c8d;">{_e(label)}</div></td>'
    )


def _title_cell(it: Item) -> str:
    label = it.title or it.number
    if it.source.startswith("https://"):
        href = html.escape(it.source.replace(" ", "%20"), quote=True)
        label_html = f'<a href="{href}">{_e(label)}</a>'
    else:
        label_html = _e(label)
    return f'<strong>{_e(it.number)}</strong><br/>{label_html}'


def subject_for(s: Summary) -> str:
    flag = f" | {s.overdue} overdue" if s.overdue else ""
    return f"[Weekly Regulatory Summary] {len(s.new_this_week)} new this week{flag}"


def render_html(s: Summary, dashboard_url: str = "") -> str:
    th = 'style="padding:8px 10px;border:1px solid #dfe3e6;background:#1b2a41;color:#fff;text-align:left;"'
    td = 'style="padding:8px 10px;border:1px solid #dfe3e6;vertical-align:top;"'

    cards = "".join([
        _card("New this week", len(s.new_this_week), "navy"),
        _card("For assessment", s.for_assessment, "amber"),
        _card("Open (applicable)", s.open_count, "navy"),
        _card("High-risk open", s.high_open, "red" if s.high_open else "green"),
        _card("Overdue", s.overdue, "red" if s.overdue else "green"),
        _card(f"Due in {DUE_SOON_DAYS} days", s.due_soon, "amber" if s.due_soon else "green"),
    ])

    regs = ", ".join(f"{n} {r}" for r, n in sorted(s.by_regulator.items())) or "none"

    new_rows = "".join(
        f'<tr><td {td}>{_e(i.regulator)} / {_e(i.type)}</td><td {td}>{_title_cell(i)}</td>'
        f'<td {td}>{_e(i.priority) or "-"}</td><td {td}>{_e(i.owner) or "<em>Unassigned</em>"}</td></tr>'
        for i in s.new_this_week[:MAX_NEW_ROWS]
    )
    more_new = (
        f'<p style="font-size:12px;color:#7f8c8d;">+ {len(s.new_this_week) - MAX_NEW_ROWS} more on the dashboard.</p>'
        if len(s.new_this_week) > MAX_NEW_ROWS else ""
    )
    new_block = (
        f'<table style="border-collapse:collapse;width:100%;"><tr>'
        f'<th {th}>Source</th><th {th}>Issuance</th><th {th}>Priority</th><th {th}>Owner</th></tr>{new_rows}</table>{more_new}'
        if s.new_this_week else "<p>No new issuances this week.</p>"
    )

    def due_label(i: Item) -> str:
        if not i.due:
            return "<em>No due date</em>"
        text = i.due.strftime("%b %d, %Y")
        return f'<span style="color:{_BADGE["red"]};font-weight:bold;">{text} (overdue)</span>' if i.due < s.as_of else text

    action_rows = "".join(
        f'<tr><td {td}>{_title_cell(i)}</td><td {td}>{_e(i.priority) or "-"}</td>'
        f'<td {td}>{_e(i.owner) or "<em>Unassigned</em>"}</td><td {td}>{due_label(i)}</td>'
        f'<td {td}>{_e(i.status) or "-"}</td></tr>'
        for i in s.action_rows
    )
    action_block = (
        f'<table style="border-collapse:collapse;width:100%;"><tr>'
        f'<th {th}>Issuance</th><th {th}>Priority</th><th {th}>Owner</th><th {th}>Due</th><th {th}>Status</th></tr>'
        f'{action_rows}</table>'
        if s.action_rows else "<p>Nothing open that needs action right now.</p>"
    )

    link = (
        f'<p><a href="{html.escape(dashboard_url, quote=True)}">Open the full dashboard</a></p>'
        if dashboard_url else ""
    )

    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;line-height:1.5;">
      <h2 style="color:#1b2a41;margin-bottom:4px;">Weekly Regulatory Summary</h2>
      <div style="color:#7f8c8d;font-size:13px;">As of {s.as_of.strftime('%A, %B %d, %Y')} &middot; {s.total_tracked} issuances tracked</div>
      <table style="border-collapse:collapse;margin:14px 0;"><tr>{cards}</tr></table>
      <h3 style="color:#1b2a41;">New this week ({regs})</h3>
      {new_block}
      <h3 style="color:#1b2a41;">Needs action</h3>
      <p style="font-size:12px;color:#7f8c8d;margin-top:0;">Open items, overdue first, then high priority, then earliest due date.</p>
      {action_block}
      {link}
      <p style="font-size:12px;color:#7f8c8d;">Automated weekly summary from the Regulatory Scraper. Figures come from the Briefings tab; update Applicability, Owner, Due Date and Status there to keep them current.</p>
    </body></html>
    """


# -- Sheet access -----------------------------------------------------------

_EMAIL_RE = re.compile(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+")


def recipients_from_values(values: Sequence[Sequence[str]]) -> List[str]:
    """Emails from the first column of the recipients tab (header row and
    anything that isn't an email address are ignored)."""
    out: List[str] = []
    for row in values:
        if not row:
            continue
        for m in _EMAIL_RE.findall(str(row[0])):
            if m not in out:
                out.append(m)
    return out
