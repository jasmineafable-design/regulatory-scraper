"""
Dashboard writer (Foundation §4.5, human-facing view).

Renders the pipeline's results into the configuration Google Sheet so people
can browse them without GitHub or email access:

  - "Briefings" tab: one row per briefing that was successfully notified (a
    log of Briefing Records, appended after Notify succeeds). Filterable.
  - "Health" tab: a single snapshot of the LATEST run only, overwritten every
    run. Deliberately no history -- the frozen foundation rejected persistent
    per-source health/failure history as unjustified complexity.
  - "Dashboard" tab: formulas and charts over the two tabs above. Built by
    tools/setup_dashboard.py, not by this module.

This is a rendering, never a source of truth: Issuance State (core/state.py)
stays authoritative for what has been seen/processed. If the two ever
disagree, state is right and the Sheet is simply stale.

Best-effort, same fail-open rule as Assess/Archive (§3.8): every public method
here swallows its own errors (logging them) and never raises, so a Sheet
problem -- missing Editor access, API quota, a deleted tab -- can never block
or delay a notification or a state commit.

Reuses the same GOOGLE_SERVICE_ACCOUNT_JSON / SHEET_ID as the config reader.
The service account must have EDITOR access to the Sheet (the config reader
alone only needed Viewer).
"""

import logging
import os
from datetime import datetime
from typing import Any, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from models.issuance import BriefingRecord

logger = logging.getLogger(__name__)

BRIEFINGS_TAB = "Briefings"
HEALTH_TAB = "Health"
DASHBOARD_TAB = "Dashboard"

# Column order is relied on by tools/setup_dashboard.py's formulas -- change
# both together. A=Date, B=Regulator, C=Type, D=Issuance No., F=Risk,
# G=Needs Review, L=Attachment, M=Official Source.
BRIEFINGS_HEADERS = [
    "Date", "Regulator", "Type", "Issuance No.", "Title", "Risk/Priority",
    "Needs Review", "Executive Summary", "Impact to Underwriting Entities",
    "Impact to Broker Entity", "Suggested Action", "Archived Copy",
    "Official Source", "Completeness",
]
REGULATOR_COL = 2      # B
ISSUANCE_NO_COL = 4    # D

# Health tab layout is also relied on by the Dashboard's formulas.
HEALTH_SOURCE_HEADER_ROW = 7

_FORMULA_TRIGGERS = ("=", "+", "-", "@")
_MAX_CELL_CHARS = 2000


def _text(value: Any) -> str:
    """Plain text safe to write with USER_ENTERED: truncated, and a leading
    =,+,-,@ is neutralised so scraped/AI text can never become a formula."""
    s = "" if value is None else str(value).strip()
    if len(s) > _MAX_CELL_CHARS:
        s = s[: _MAX_CELL_CHARS - 1] + "…"
    if s.startswith(_FORMULA_TRIGGERS):
        s = "'" + s
    return s


def _type_of(briefing: BriefingRecord) -> str:
    """Category without its regulator prefix (IC-CL -> CL), same rule as the
    attachment filenames (core/archive.py)."""
    category = (briefing.source_category or "").upper()
    prefix = f"{(briefing.source_regulator or '').upper()}-"
    return category[len(prefix):] if category.startswith(prefix) else category


def _archived_copy_cell(b: BriefingRecord) -> str:
    """The Drive link when there is one (left as-is so it stays clickable),
    else the attached file's name, else UNAVAILABLE."""
    link = (b.archived_document_link or "").strip()
    if link.startswith("https://"):
        return link
    return _text(b.attachment_filename or "UNAVAILABLE")


def _describe(err: BaseException) -> str:
    return f"{type(err).__name__}: {str(err).strip()[:400] or '(no message)'}"


class DashboardWriter:
    def __init__(self, config_reader: Optional[object] = None, tz_name: str = "Asia/Manila"):
        self._gc = getattr(config_reader, "_gc", None)
        spreadsheet_id = getattr(config_reader, "spreadsheet_id", None)
        # Anything that isn't a real string id (unset, or a test double) means
        # "no Sheet to write to".
        self._spreadsheet_id = spreadsheet_id if isinstance(spreadsheet_id, str) else None
        try:
            self._tz = ZoneInfo(tz_name)
        except Exception:
            self._tz = ZoneInfo("UTC")

    # -- availability --------------------------------------------------------

    @property
    def enabled(self) -> bool:
        if os.getenv("DASHBOARD_DISABLED"):
            # Set by tools/test_digest_email.py so its replayed "new"
            # issuances don't pollute the real log.
            return False
        return bool(self._gc and self._spreadsheet_id)

    def _spreadsheet(self):
        return self._gc.open_by_key(self._spreadsheet_id)

    # -- tab helpers ---------------------------------------------------------

    def _get_or_create_tab(self, spreadsheet, title: str, rows: int, cols: int):
        import gspread

        try:
            return spreadsheet.worksheet(title), False
        except gspread.exceptions.WorksheetNotFound:
            return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols), True

    def ensure_briefings_tab(self, spreadsheet):
        ws, created = self._get_or_create_tab(spreadsheet, BRIEFINGS_TAB, rows=1000, cols=len(BRIEFINGS_HEADERS))
        if created:
            ws.update(values=[BRIEFINGS_HEADERS], range_name="A1", value_input_option="RAW")
            try:  # cosmetic only -- never let formatting failure matter
                ws.freeze(rows=1)
                ws.format("A1:N1", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.17, "green": 0.24, "blue": 0.31},
                                    "horizontalAlignment": "CENTER"})
                ws.format("A1:N1", {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}})
                ws.format("A2:N", {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"})
                ws.format("A2:A", {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}})
                ws.set_basic_filter()
            except Exception as e:
                logger.warning(f"Dashboard: Briefings tab formatting skipped ({_describe(e)})")
        return ws

    def ensure_health_tab(self, spreadsheet):
        ws, _ = self._get_or_create_tab(spreadsheet, HEALTH_TAB, rows=60, cols=3)
        return ws

    # -- Briefings log -------------------------------------------------------

    def log_briefings(self, briefings: Sequence[BriefingRecord]) -> int:
        """Appends one row per briefing not already logged. Returns rows
        added. Never raises."""
        if not briefings or not self.enabled:
            return 0
        try:
            ss = self._spreadsheet()
            ws = self.ensure_briefings_tab(ss)

            regulators = ws.col_values(REGULATOR_COL)[1:]
            numbers = ws.col_values(ISSUANCE_NO_COL)[1:]
            already = {(r.strip().upper(), n.strip()) for r, n in zip(regulators, numbers)}

            today = datetime.now(self._tz).strftime("%Y-%m-%d")
            rows: List[List[str]] = []
            for b in briefings:
                key = ((b.source_regulator or "").strip().upper(), (b.issuance_identifier or "").strip())
                if key in already:
                    continue  # a re-sent briefing must not double-count
                already.add(key)
                risk = (b.risk_priority_level or "UNAVAILABLE").strip()
                rows.append([
                    today,
                    _text(b.source_regulator),
                    _text(_type_of(b)),
                    _text(b.issuance_identifier),
                    _text(b.issuance_title),
                    _text(risk),
                    "Yes" if risk.upper() == "HIGH" else "No",
                    _text(b.executive_summary),
                    _text(b.insurance_entity_impact),
                    _text(b.brokerage_entity_impact),
                    _text(b.suggested_action),
                    _archived_copy_cell(b),
                    (b.official_source_link or "").strip(),  # left as-is so it stays a clickable link
                    _text(b.completeness_status),
                ])

            if rows:
                ws.append_rows(rows, value_input_option="USER_ENTERED", table_range="A1")
                logger.info(f"Dashboard: logged {len(rows)} briefing(s) to the '{BRIEFINGS_TAB}' tab.")
            return len(rows)
        except Exception as e:
            logger.error(
                f"Dashboard: could not log briefings ({_describe(e)}). The notification and "
                "state commit are unaffected. If this is a 403, the service account needs "
                "Editor access to the Sheet."
            )
            return 0

    # -- Health snapshot -----------------------------------------------------

    def write_health_snapshot(
        self,
        is_opening_check: bool,
        total_new: int,
        notified: int,
        source_status: Sequence[Tuple[str, str, str]],
    ) -> bool:
        """Overwrites the Health tab with the latest run only. source_status
        is a list of (source, status, detail). Never raises."""
        if not self.enabled:
            return False
        try:
            ss = self._spreadsheet()
            ws = self.ensure_health_tab(ss)

            failed = sum(1 for _, status, _ in source_status if status == "FAILED")
            result = "All sources OK" if not failed else f"{failed} source(s) failed"
            grid: List[List[Any]] = [
                ["Last run", datetime.now(self._tz).strftime("%Y-%m-%d %H:%M")],
                ["Run type", "Opening check" if is_opening_check else "Recurring check"],
                ["New issuances found", total_new],
                ["Notified", notified],
                ["Result", result],
                [],
                ["Source", "Status", "Detail"],
            ]
            for source, status, detail in source_status:
                # RAW write: no formula risk, so no apostrophe-escaping needed.
                grid.append([source, status, str(detail)[:300]])

            ws.clear()
            ws.update(values=grid, range_name="A1", value_input_option="RAW")
            return True
        except Exception as e:
            logger.error(f"Dashboard: could not write health snapshot ({_describe(e)}). Run is unaffected.")
            return False
