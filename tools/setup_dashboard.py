"""
Builds (or rebuilds) the "Dashboard" tab in the configuration Google Sheet and
brings the "Briefings" tab up to the current layout.

DASHBOARD (oversight only -- the detail lives on the Briefings tab):
  - Five cards: For Assessment | Applicable / Open | High-Risk Open | Overdue |
    Due Soon (30 days).
  - "Action Required": up to 20 items that need assessment or action, most
    urgent first (overdue, then High review priority, then earliest due date,
    then newest).
  - One compact scraper line: last run, result, sources failing, archive link.

  Everything is a formula over the Briefings and Health tabs, so it updates by
  itself. Re-running this tool DELETES and recreates only the Dashboard tab
  (manual edits to that tab are lost).

BRIEFINGS UPGRADE (never touches data rows): rewrites the header row, adds the
team's six columns (Applicability, Impact/Risk, Required Action, Owner, Due
Date, Status) with dropdowns, hides the legacy "Needs Review" column.

HOW "OPEN" IS DEFINED
  Open       = Applicability is Yes or Partially, and Status is not Closed /
               Not Applicable (a blank Status counts as open).
  For Assessment = no Applicability chosen yet.
  Applicability "No" drops the item from every card and table.

Run from GitHub: Actions -> "Setup Dashboard Tab" -> Run workflow. Or locally
with GOOGLE_SERVICE_ACCOUNT_JSON and SHEET_ID set:

    python tools/setup_dashboard.py              # build/rebuild
    python tools/setup_dashboard.py --demo add   # also add 7 clearly-marked DEMO rows
    python tools/setup_dashboard.py --demo remove

Demo rows are only for checking the layout. Expected cards with the demo rows
and no real data: For Assessment 2 | Applicable/Open 3 | High-Risk Open 1 |
Overdue 1 | Due Soon 1.

The service account needs EDITOR access to the Sheet.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.dashboard import (  # noqa: E402
    BRIEFINGS_HEADERS,
    BRIEFINGS_TAB,
    DASHBOARD_TAB,
    HEALTH_TAB,
    DashboardWriter,
)
from core.sheets_config import SheetsConfigReader  # noqa: E402

B = BRIEFINGS_TAB
H = HEALTH_TAB

DARK = {"red": 0.17, "green": 0.24, "blue": 0.31}
WHITE = {"red": 1, "green": 1, "blue": 1}
LIGHT = {"red": 0.96, "green": 0.97, "blue": 0.97}
RED_BG = {"red": 0.96, "green": 0.80, "blue": 0.78}
AMBER_BG = {"red": 1.0, "green": 0.92, "blue": 0.70}
RED_TEXT = {"red": 0.75, "green": 0.10, "blue": 0.10}
GRAY_TEXT = {"red": 0.45, "green": 0.50, "blue": 0.50}

CARDS_LABEL_ROW = 4
CARDS_VALUE_ROW = 5
ACTION_LABEL_ROW = 7
ACTION_HEADER_ROW = 8
ACTION_FIRST_ROW = 9
ACTION_MAX_ROWS = 20
ACTION_LAST_ROW = ACTION_FIRST_ROW + ACTION_MAX_ROWS - 1   # 28
SCRAPER_LABEL_ROW = 30
SCRAPER_HEADER_ROW = 31
SCRAPER_VALUE_ROW = 32

# A row is "open": has an issuance, applicability is Yes/Partially, and status
# is not Closed / Not Applicable. Shared by every card.
OPEN = (
    f'({B}!D2:D<>"")*ISNUMBER(MATCH({B}!O2:O,{{"Yes","Partially"}},0))'
    f'*(1-ISNUMBER(MATCH({B}!T2:T,{{"Closed","Not Applicable"}},0)))'
)

# Sorted, filtered Action Required table. Output columns:
# Priority | Regulator | Issuance No. | Owner | Due Date | Status | Title
# (an 8th sort-key column is built and then dropped by ARRAY_CONSTRAIN).
ACTION_FORMULA = (
    "=IFERROR(LET("
    f"ids,{B}!D2:D,"
    f"appl,{B}!O2:O,"
    f"stat,{B}!T2:T,"
    f"due,{B}!S2:S,"
    f"prio,{B}!F2:F,"
    f"added,{B}!A2:A,"
    'here,ids<>"",'
    'isOpen,here*ISNUMBER(MATCH(appl,{"Yes","Partially"},0))*(1-ISNUMBER(MATCH(stat,{"Closed","Not Applicable"},0))),'
    'isNew,here*(appl=""),'
    'late,isOpen*(due<>"")*(due<TODAY()),'
    'high,--(prio="High"),'
    "sortKey,(1-late)*1E12+(1-high)*1E11+IF(due=\"\",99999,IFERROR(due+0,99999))*1E5+(99999-IFERROR(added+0,0)),"
    'shownStatus,IF(isNew=1,"For Assessment",IF(stat="","Action Required",stat)),'
    f"picked,FILTER({{prio,{B}!B2:B,ids,{B}!R2:R,due,shownStatus,{B}!E2:E,sortKey}},(isOpen+isNew)>0),"
    f"ARRAY_CONSTRAIN(SORT(picked,8,TRUE),{ACTION_MAX_ROWS},7)"
    '),"Nothing needs attention right now")'
)


def _cells():
    """(A1 address, value) pairs. Formulas use USER_ENTERED."""
    c = []
    c.append(("A1", "Regulatory Monitoring — Dashboard"))
    c.append(("A2", "New issuances start as For Assessment. Details and team assessment are on the 'Briefings' tab. Formulas only — do not type over them."))

    cards = [
        ("A", "For Assessment", f'=COUNTIFS({B}!D2:D,"<>",{B}!O2:O,"")'),
        ("B", "Applicable / Open", f"=SUMPRODUCT({OPEN})"),
        ("C", "High-Risk Open", f'=SUMPRODUCT({OPEN}*({B}!F2:F="High"))'),
        ("D", "Overdue", f'=SUMPRODUCT({OPEN}*({B}!S2:S<>"")*({B}!S2:S<TODAY()))'),
        ("E", "Due Soon (30 days)",
         f'=SUMPRODUCT({OPEN}*({B}!S2:S<>"")*({B}!S2:S>=TODAY())*({B}!S2:S<=TODAY()+30))'),
    ]
    for col, label, formula in cards:
        c.append((f"{col}{CARDS_LABEL_ROW}", label))
        c.append((f"{col}{CARDS_VALUE_ROW}", formula))

    c.append((f"A{ACTION_LABEL_ROW}", "Action Required"))
    c.append((
        f"D{ACTION_LABEL_ROW}",
        f'=IF(A{CARDS_VALUE_ROW}+B{CARDS_VALUE_ROW}>{ACTION_MAX_ROWS},'
        f'"Showing the top {ACTION_MAX_ROWS} of "&(A{CARDS_VALUE_ROW}+B{CARDS_VALUE_ROW})&" — see the Briefings tab for the rest","")',
    ))
    for col, label in zip("ABCDEFG", ["Priority", "Regulator", "Issuance No.", "Owner", "Due Date", "Status", "Title"]):
        c.append((f"{col}{ACTION_HEADER_ROW}", label))
    c.append((f"A{ACTION_FIRST_ROW}", ACTION_FORMULA))

    # Scraper health: one compact line.
    c.append((f"A{SCRAPER_LABEL_ROW}", "Scraper"))
    c.append((f"A{SCRAPER_HEADER_ROW}", "Last run"))
    c.append((f"C{SCRAPER_HEADER_ROW}", "Result"))
    c.append((f"E{SCRAPER_HEADER_ROW}", "Sources failing"))
    c.append((f"A{SCRAPER_VALUE_ROW}", f'=IF({H}!B1="","(no run recorded yet)",{H}!B1)'))
    c.append((f"C{SCRAPER_VALUE_ROW}", f'=IF({H}!B5="","—",{H}!B5)'))
    c.append((f"E{SCRAPER_VALUE_ROW}", f'=COUNTIF({H}!B8:B,"FAILED")'))
    archive_url = os.getenv("ARCHIVE_FOLDER_URL", "").strip()
    if archive_url.startswith("https://"):
        c.append((f"F{SCRAPER_HEADER_ROW}", "Document archive"))
        c.append((f"F{SCRAPER_VALUE_ROW}", f'=HYPERLINK("{archive_url}","Open the Regulatory Archive")'))
    return c


def _rect(sheet_id, r0, r1, c0, c1):
    """1-based inclusive rows, 0-based column indexes [c0, c1)."""
    return {"sheetId": sheet_id, "startRowIndex": r0 - 1, "endRowIndex": r1,
            "startColumnIndex": c0, "endColumnIndex": c1}


def build_requests(sheet_id: int):
    requests = []

    def fmt(rect, cell_format, fields):
        return {"repeatCell": {"range": rect, "cell": {"userEnteredFormat": cell_format}, "fields": fields}}

    def cond(rect, condition, fmt_):
        return {"addConditionalFormatRule": {"index": 0, "rule": {
            "ranges": [rect], "booleanRule": {"condition": condition, "format": fmt_}}}}

    # Title / subtitle
    requests.append(fmt(_rect(sheet_id, 1, 1, 0, 1), {"textFormat": {"bold": True, "fontSize": 18}}, "userEnteredFormat.textFormat"))
    requests.append(fmt(_rect(sheet_id, 2, 2, 0, 1), {"textFormat": {"italic": True, "foregroundColor": GRAY_TEXT}},
                        "userEnteredFormat.textFormat"))

    # Cards
    requests.append(fmt(_rect(sheet_id, CARDS_LABEL_ROW, CARDS_LABEL_ROW, 0, 5),
                        {"backgroundColor": DARK, "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE", "wrapStrategy": "WRAP",
                         "textFormat": {"bold": True, "foregroundColor": WHITE, "fontSize": 10}},
                        "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat)"))
    requests.append(fmt(_rect(sheet_id, CARDS_VALUE_ROW, CARDS_VALUE_ROW, 0, 5),
                        {"backgroundColor": LIGHT, "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
                         "textFormat": {"bold": True, "fontSize": 20}},
                        "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"))
    # Colour only when it matters: amber = needs assessment, red = high-risk / overdue.
    gt0 = {"type": "NUMBER_GREATER", "values": [{"userEnteredValue": "0"}]}
    requests.append(cond(_rect(sheet_id, CARDS_VALUE_ROW, CARDS_VALUE_ROW, 0, 1), gt0, {"backgroundColor": AMBER_BG}))
    requests.append(cond(_rect(sheet_id, CARDS_VALUE_ROW, CARDS_VALUE_ROW, 2, 3), gt0, {"backgroundColor": RED_BG, "textFormat": {"foregroundColor": RED_TEXT}}))
    requests.append(cond(_rect(sheet_id, CARDS_VALUE_ROW, CARDS_VALUE_ROW, 3, 4), gt0, {"backgroundColor": RED_BG, "textFormat": {"foregroundColor": RED_TEXT}}))
    requests.append(cond(_rect(sheet_id, CARDS_VALUE_ROW, CARDS_VALUE_ROW, 4, 5), gt0, {"backgroundColor": AMBER_BG}))

    # Section labels
    for row in (ACTION_LABEL_ROW, SCRAPER_LABEL_ROW):
        requests.append(fmt(_rect(sheet_id, row, row, 0, 1), {"textFormat": {"bold": True, "fontSize": 13}}, "userEnteredFormat.textFormat"))
    requests.append(fmt(_rect(sheet_id, ACTION_LABEL_ROW, ACTION_LABEL_ROW, 3, 4),
                        {"textFormat": {"italic": True, "foregroundColor": GRAY_TEXT}}, "userEnteredFormat.textFormat"))

    # Action table
    requests.append(fmt(_rect(sheet_id, ACTION_HEADER_ROW, ACTION_HEADER_ROW, 0, 7),
                        {"backgroundColor": DARK, "textFormat": {"bold": True, "foregroundColor": WHITE}},
                        "userEnteredFormat(backgroundColor,textFormat)"))
    requests.append(fmt(_rect(sheet_id, ACTION_FIRST_ROW, ACTION_LAST_ROW, 0, 7),
                        {"verticalAlignment": "TOP", "wrapStrategy": "WRAP"}, "userEnteredFormat(verticalAlignment,wrapStrategy)"))
    requests.append(fmt(_rect(sheet_id, ACTION_FIRST_ROW, ACTION_LAST_ROW, 4, 5),
                        {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}, "userEnteredFormat.numberFormat"))
    first, last = ACTION_FIRST_ROW, ACTION_LAST_ROW
    requests.append(cond(_rect(sheet_id, first, last, 0, 1),
                         {"type": "TEXT_EQ", "values": [{"userEnteredValue": "High"}]},
                         {"textFormat": {"bold": True, "foregroundColor": RED_TEXT}}))
    requests.append(cond(_rect(sheet_id, first, last, 4, 5),
                         {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": f"=AND(ISNUMBER($E{first}),$E{first}<TODAY())"}]},
                         {"backgroundColor": RED_BG, "textFormat": {"bold": True, "foregroundColor": RED_TEXT}}))
    requests.append(cond(_rect(sheet_id, first, last, 5, 6),
                         {"type": "TEXT_EQ", "values": [{"userEnteredValue": "For Assessment"}]},
                         {"backgroundColor": AMBER_BG}))

    # Scraper line
    requests.append(fmt(_rect(sheet_id, SCRAPER_HEADER_ROW, SCRAPER_HEADER_ROW, 0, 7),
                        {"textFormat": {"bold": True, "foregroundColor": GRAY_TEXT, "fontSize": 9}}, "userEnteredFormat.textFormat"))
    requests.append(fmt(_rect(sheet_id, SCRAPER_VALUE_ROW, SCRAPER_VALUE_ROW, 0, 7),
                        {"textFormat": {"fontSize": 11}, "horizontalAlignment": "LEFT"}, "userEnteredFormat(textFormat,horizontalAlignment)"))
    requests.append(cond(_rect(sheet_id, SCRAPER_VALUE_ROW, SCRAPER_VALUE_ROW, 4, 5), gt0,
                         {"backgroundColor": RED_BG, "textFormat": {"foregroundColor": RED_TEXT, "bold": True}}))
    requests.append(cond(_rect(sheet_id, SCRAPER_VALUE_ROW, SCRAPER_VALUE_ROW, 2, 3),
                         {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "failed"}]},
                         {"textFormat": {"foregroundColor": RED_TEXT, "bold": True}}))

    # Column widths: A..G (Title, last, is the wide one)
    for idx, px in enumerate([120, 110, 160, 130, 120, 150, 460]):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": idx, "endIndex": idx + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})
    requests.append({"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": CARDS_LABEL_ROW - 1, "endIndex": CARDS_LABEL_ROW},
        "properties": {"pixelSize": 36}, "fields": "pixelSize"}})
    requests.append({"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": CARDS_VALUE_ROW - 1, "endIndex": CARDS_VALUE_ROW},
        "properties": {"pixelSize": 48}, "fields": "pixelSize"}})
    requests.append({"updateSheetProperties": {
        "properties": {"sheetId": sheet_id, "gridProperties": {"hideGridlines": True}},
        "fields": "gridProperties.hideGridlines"}})
    return requests


def demo_rows(today=None):
    """Seven clearly-marked rows that exercise every card and the table order.
    Regulator is 'DEMO', so they can be found and removed again."""
    today = today or datetime.now()
    d = lambda days: (today + timedelta(days=days)).strftime("%Y-%m-%d")  # noqa: E731
    base = ["DEMO", "TEST"]

    def row(n, title, risk, appl, action, owner, due, status):
        return [d(0), *base, f"DEMO-{n}", f"DEMO — {title}", risk, "Yes" if risk == "High" else "No", "Sample summary.", "Sample impact.",
                "Sample impact.", "Sample action.", "—", "https://example.com", "complete",
                appl, "", action, owner, due, status]

    return [
        row(1, "High priority, not yet assessed", "High", "", "", "", "", "For Assessment"),
        row(2, "Medium priority, not yet assessed", "Medium", "", "", "", "", "For Assessment"),
        row(3, "Applicable, High, OVERDUE", "High", "Yes", "File amended return", "Maria", d(-10), "Action Required"),
        row(4, "Applicable, due in 10 days", "Medium", "Yes", "Update policy", "Jun", d(10), "In Progress"),
        row(5, "Partially applicable, no due date", "Low", "Partially", "Review clause 4", "", "", "Action Required"),
        row(6, "Not applicable (should not appear)", "High", "No", "", "", "", "Not Applicable"),
        row(7, "Closed (should not appear)", "Medium", "Yes", "Done", "Maria", d(-30), "Closed"),
    ]


def _handle_demo(ws, mode):
    if mode == "add":
        existing = {v.strip() for v in ws.col_values(4)[1:]}
        rows = [r for r in demo_rows() if r[3] not in existing]
        if rows:
            ws.append_rows(rows, value_input_option="USER_ENTERED", table_range="A1")
        print(f"Added {len(rows)} DEMO row(s) to '{B}'. Remove them with --demo remove.")
    elif mode == "remove":
        regulators = ws.col_values(2)
        to_delete = [i + 1 for i, v in enumerate(regulators) if i > 0 and v.strip().upper() == "DEMO"]
        for row_number in reversed(to_delete):
            ws.delete_rows(row_number)
        print(f"Removed {len(to_delete)} DEMO row(s) from '{B}'.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", choices=["none", "add", "remove"], default="none",
                        help="Add or remove clearly-marked DEMO rows for checking the layout.")
    args = parser.parse_args()

    reader = SheetsConfigReader()
    writer = DashboardWriter(reader)
    if not writer.enabled:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON and SHEET_ID must both be set (and valid).")
        return 1

    ss = writer._spreadsheet()

    # Briefings: create if missing, otherwise upgrade in place (headers,
    # team columns, dropdowns) -- data rows are never touched.
    briefings_ws = writer.upgrade_briefings_tab(ss)
    writer.ensure_health_tab(ss)
    print(f"'{B}' tab is up to date ({len(BRIEFINGS_HEADERS)} columns).")

    if args.demo != "none":
        _handle_demo(briefings_ws, args.demo)

    import gspread

    try:
        ss.del_worksheet(ss.worksheet(DASHBOARD_TAB))
        print(f"Removed the old '{DASHBOARD_TAB}' tab.")
    except gspread.exceptions.WorksheetNotFound:
        pass

    ws = ss.add_worksheet(title=DASHBOARD_TAB, rows=60, cols=8, index=0)
    data = [{"range": addr, "values": [[val]]} for addr, val in _cells()]
    ws.batch_update(data, value_input_option="USER_ENTERED")
    ss.batch_update({"requests": build_requests(ws.id)})
    print(f"Built the '{DASHBOARD_TAB}' tab ({len(data)} cells). It's the first tab.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
