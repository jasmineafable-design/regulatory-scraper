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
# both together.
#   A..N  written by the pipeline (A=Date, B=Regulator, C=Type, D=Issuance No.,
#         E=Title, F=Review Priority, G=Needs Review [hidden, legacy],
#         L=Archived Copy, M=Official Source, N=Completeness).
#   O..T  filled in by the Tax/Compliance team -- the pipeline NEVER writes to
#         these on an existing row (it only appends new rows, setting Status
#         to "For Assessment"):
#         O=Applicability, P=Impact/Risk, Q=Required Action, R=Owner,
#         S=Due Date, T=Status.
BRIEFINGS_HEADERS = [
    "Date", "Regulator", "Type", "Issuance No.", "Title", "Review Priority",
    "Needs Review", "Executive Summary", "Impact to Underwriting Entities",
    "Impact to Broker Entity", "Suggested Action", "Archived Copy",
    "Official Source", "Completeness",
    "Applicability", "Impact/Risk", "Required Action", "Owner", "Due Date", "Status",
]
PIPELINE_COLS = 14           # A..N
TEAM_COLS_START = 14         # 0-based index of O
APPLICABILITY_OPTIONS = ["Yes", "No", "Partially"]
STATUS_OPTIONS = ["For Assessment", "Action Required", "In Progress", "Closed", "Not Applicable"]
DEFAULT_STATUS = "For Assessment"

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


def briefings_format_requests(sheet_id: int) -> List[dict]:
    """Sheets API requests that give the Briefings tab its look and its
    team-entry dropdowns. Idempotent -- safe to re-apply on an existing tab."""
    dark = {"red": 0.17, "green": 0.24, "blue": 0.31}
    amber = {"red": 1.0, "green": 0.90, "blue": 0.60}
    white = {"red": 1, "green": 1, "blue": 1}
    n = len(BRIEFINGS_HEADERS)

    def rect(r0, r1, c0, c1):
        r = {"sheetId": sheet_id, "startRowIndex": r0, "startColumnIndex": c0, "endColumnIndex": c1}
        if r1 is not None:
            r["endRowIndex"] = r1
        return r

    def validation(col, condition):
        return {"setDataValidation": {
            "range": rect(1, None, col, col + 1),   # row 2 down, unbounded (covers appended rows)
            "rule": {"condition": condition, "strict": True, "showCustomUi": True},
        }}

    reqs = [
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 4}},
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }},
        # Header: dark for scraper columns, amber for the team's columns.
        {"repeatCell": {"range": rect(0, 1, 0, TEAM_COLS_START),
                        "cell": {"userEnteredFormat": {"backgroundColor": dark, "horizontalAlignment": "CENTER",
                                                       "wrapStrategy": "WRAP",
                                                       "textFormat": {"bold": True, "foregroundColor": white}}},
                        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,wrapStrategy,textFormat)"}},
        {"repeatCell": {"range": rect(0, 1, TEAM_COLS_START, n),
                        "cell": {"userEnteredFormat": {"backgroundColor": amber, "horizontalAlignment": "CENTER",
                                                       "wrapStrategy": "WRAP",
                                                       "textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,wrapStrategy,textFormat)"}},
        # Body
        {"repeatCell": {"range": rect(1, None, 0, n),
                        "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
                        "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}},
        {"repeatCell": {"range": rect(1, None, 0, 1),
                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
                        "fields": "userEnteredFormat.numberFormat"}},
        {"repeatCell": {"range": rect(1, None, 18, 19),   # S = Due Date
                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
                        "fields": "userEnteredFormat.numberFormat"}},
        # Hide the legacy "Needs Review" column (G): the Dashboard now decides
        # what needs attention from Applicability/Status/Due Date.
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 6, "endIndex": 7},
            "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}},
        # Team-entry dropdowns / date check.
        validation(14, {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in APPLICABILITY_OPTIONS]}),
        validation(19, {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in STATUS_OPTIONS]}),
        validation(18, {"type": "DATE_IS_VALID"}),
        # Filter across all columns (replaces any older, narrower filter).
        {"setBasicFilter": {"filter": {"range": {"sheetId": sheet_id, "startRowIndex": 0,
                                                 "startColumnIndex": 0, "endColumnIndex": n}}}},
    ]
    # Column widths: readable text columns, narrow short ones.
    widths = {0: 90, 1: 80, 2: 90, 3: 150, 4: 280, 5: 100, 7: 300, 8: 220, 9: 220, 10: 220,
              11: 150, 12: 150, 13: 100, 14: 110, 15: 220, 16: 220, 17: 120, 18: 100, 19: 130}
    for idx, px in widths.items():
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": idx, "endIndex": idx + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})
    return reqs


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
            self.format_briefings_tab(spreadsheet, ws)
        return ws

    def upgrade_briefings_tab(self, spreadsheet):
        """Brings an EXISTING Briefings tab up to the current layout without
        touching any data row: rewrites only the header row, adds the team's
        columns if missing, and re-applies dropdowns/formatting. Used by
        tools/setup_dashboard.py."""
        ws = self.ensure_briefings_tab(spreadsheet)
        if ws.col_count < len(BRIEFINGS_HEADERS):
            ws.resize(cols=len(BRIEFINGS_HEADERS))
        ws.update(values=[BRIEFINGS_HEADERS], range_name="A1", value_input_option="RAW")
        self.format_briefings_tab(spreadsheet, ws)
        return ws

    def format_briefings_tab(self, spreadsheet, ws) -> None:
        """Cosmetic + dropdowns; best-effort, never raises."""
        try:
            spreadsheet.batch_update({"requests": briefings_format_requests(ws.id)})
        except Exception as e:
            logger.warning(f"Dashboard: Briefings tab formatting skipped ({_describe(e)})")

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
                    # Team-filled columns O..T: left blank for the team, except
                    # Status, which starts every briefing at "For Assessment".
                    "", "", "", "", "", DEFAULT_STATUS,
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
