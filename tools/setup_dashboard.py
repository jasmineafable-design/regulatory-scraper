"""
Builds (or rebuilds) the "Dashboard" tab in the configuration Google Sheet:
KPI cards, counts by regulator / month / risk / type, three charts, the 15
latest briefings, and every High-risk ("needs review") item.

Everything on the tab is a formula over the "Briefings" and "Health" tabs, so
it updates by itself as the pipeline logs new briefings -- no code runs after
this setup. Re-running this tool DELETES and recreates the Dashboard tab
(handy after layout changes; any manual edits to that tab are lost). It never
touches the Briefings or Health tabs' data.

Run it from GitHub: Actions -> "Setup Dashboard Tab" -> Run workflow. Or
locally with GOOGLE_SERVICE_ACCOUNT_JSON and SHEET_ID set:

    python tools/setup_dashboard.py

The service account needs EDITOR access to the Sheet.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.dashboard import (  # noqa: E402
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
LIGHT = {"red": 0.97, "green": 0.98, "blue": 0.98}
RED_BG = {"red": 0.99, "green": 0.88, "blue": 0.87}

# Row/column anchors (0-based indexes are derived from these 1-based rows).
SMALL_TABLES_ROW = 7          # header row of the four small tables
CHARTS_ANCHOR_ROW = 21        # charts sit over A21:L37 (no data there)
LATEST_LABEL_ROW = 39
LATEST_QUERY_ROW = 40         # header + 15 rows -> 40..55
REVIEW_LABEL_ROW = 58
REVIEW_QUERY_ROW = 59         # spills downward, last block on the tab


def _cells():
    """(A1 address, value) pairs. Formulas use USER_ENTERED."""
    c = []
    c.append(("A1", "Regulatory Scraper — Dashboard"))
    c.append(("A2", f"Live view of the '{B}' log and the latest run. Formulas only — do not type over them."))

    # KPI cards (labels row 3, values row 4)
    for col, label, formula in [
        ("A", "Briefings logged", f"=COUNTA({B}!D2:D)"),
        ("B", "This month", f'=COUNTIFS({B}!A2:A,">="&DATE(YEAR(TODAY()),MONTH(TODAY()),1))'),
        ("C", "Needs review (High risk)", f'=COUNTIF({B}!G2:G,"Yes")'),
        ("D", "Last run", f"={H}!B1"),
        ("E", "Last run result", f"={H}!B5"),
        ("G", "Sources failing", f'=COUNTIF({H}!B8:B,"FAILED")'),
    ]:
        c.append((f"{col}3", label))
        c.append((f"{col}4", formula))

    # Link to the shared Drive archive (same ARCHIVE_FOLDER_URL as the emails).
    archive_url = os.getenv("ARCHIVE_FOLDER_URL", "").strip()
    if archive_url.startswith("https://"):
        c.append(("I3", "Document archive"))
        c.append(("I4", f'=HYPERLINK("{archive_url}","Open the Regulatory Archive")'))

    r = SMALL_TABLES_ROW
    # By regulator (fixed rows so the chart range is exact)
    c.append((f"A{r - 1}", "By regulator"))
    c += [(f"A{r}", "Regulator"), (f"B{r}", "Briefings")]
    for i, reg in enumerate(["BIR", "IC", "SEC"], start=1):
        c.append((f"A{r + i}", reg))
        c.append((f"B{r + i}", f'=COUNTIF({B}!$B$2:$B,A{r + i})'))

    # By month: last 12 months, fixed rows
    c.append((f"D{r - 1}", "By month (last 12)"))
    c += [(f"D{r}", "Month"), (f"E{r}", "Briefings")]
    for i in range(1, 13):
        if i == 1:
            c.append((f"D{r + i}", "=EDATE(DATE(YEAR(TODAY()),MONTH(TODAY()),1),-11)"))
        else:
            c.append((f"D{r + i}", f"=EDATE(D{r + i - 1},1)"))
        c.append((f"E{r + i}", f'=COUNTIFS({B}!$A$2:$A,">="&D{r + i},{B}!$A$2:$A,"<"&EDATE(D{r + i},1))'))

    # By risk (fixed rows)
    c.append((f"G{r - 1}", "By risk level"))
    c += [(f"G{r}", "Risk"), (f"H{r}", "Briefings")]
    for i, risk in enumerate(["High", "Medium", "Low"], start=1):
        c.append((f"G{r + i}", risk))
        c.append((f"H{r + i}", f'=COUNTIF({B}!$F$2:$F,G{r + i})'))

    # By regulator & type (spills)
    c.append((f"J{r - 1}", "By regulator and type"))
    c.append((
        f"J{r}",
        f'=IFERROR(QUERY({B}!A1:N,"select B, C, count(D) where D is not null group by B, C order by B, C '
        f"label B 'Regulator', C 'Type', count(D) 'Briefings'\",1),\"No briefings logged yet\")",
    ))

    c.append((f"A{CHARTS_ANCHOR_ROW - 1}", "Charts"))

    c.append((f"A{LATEST_LABEL_ROW}", "Latest 15 briefings"))
    c.append((
        f"A{LATEST_QUERY_ROW}",
        f'=IFERROR(QUERY({B}!A1:N,"select A, B, C, D, E, F, L, M order by A desc limit 15",1),"No briefings logged yet")',
    ))

    c.append((f"A{REVIEW_LABEL_ROW}", "Needs review — High-risk briefings"))
    c.append((
        f"A{REVIEW_QUERY_ROW}",
        f"=IFERROR(QUERY({B}!A1:N,\"select A, B, C, D, E, K, M where G = 'Yes' order by A desc\",1),"
        '"No High-risk briefings yet")',
    ))
    return c


def _rect(sheet_id, a1_start_row, a1_end_row, start_col, end_col):
    """1-based inclusive rows, 0-based column indexes [start_col, end_col)."""
    return {
        "sheetId": sheet_id,
        "startRowIndex": a1_start_row - 1,
        "endRowIndex": a1_end_row,
        "startColumnIndex": start_col,
        "endColumnIndex": end_col,
    }


def _bar_chart(sheet_id, title, domain_rect, series_rect, anchor_col, kind="COLUMN"):
    return {"addChart": {"chart": {
        "spec": {
            "title": title,
            "basicChart": {
                "chartType": kind,
                "legendPosition": "NO_LEGEND",
                "headerCount": 1,
                "domains": [{"domain": {"sourceRange": {"sources": [domain_rect]}}}],
                "series": [{"series": {"sourceRange": {"sources": [series_rect]}}, "targetAxis": "LEFT_AXIS"}],
            },
        },
        "position": {"overlayPosition": {
            "anchorCell": {"sheetId": sheet_id, "rowIndex": CHARTS_ANCHOR_ROW - 1, "columnIndex": anchor_col},
            "widthPixels": 330, "heightPixels": 290,
        }},
    }}}


def _pie_chart(sheet_id, title, domain_rect, series_rect, anchor_col):
    return {"addChart": {"chart": {
        "spec": {
            "title": title,
            "pieChart": {
                "legendPosition": "RIGHT_LEGEND",
                "domain": {"sourceRange": {"sources": [domain_rect]}},
                "series": {"sourceRange": {"sources": [series_rect]}},
            },
        },
        "position": {"overlayPosition": {
            "anchorCell": {"sheetId": sheet_id, "rowIndex": CHARTS_ANCHOR_ROW - 1, "columnIndex": anchor_col},
            "widthPixels": 330, "heightPixels": 290,
        }},
    }}}


def build_requests(sheet_id: int):
    r = SMALL_TABLES_ROW
    requests = []

    # Charts: regulator (A:B), month (D:E), risk (G:H); header row included.
    requests.append(_bar_chart(sheet_id, "Briefings by regulator",
                               _rect(sheet_id, r, r + 3, 0, 1), _rect(sheet_id, r, r + 3, 1, 2), anchor_col=0))
    requests.append(_bar_chart(sheet_id, "Briefings by month",
                               _rect(sheet_id, r, r + 12, 3, 4), _rect(sheet_id, r, r + 12, 4, 5), anchor_col=4))
    requests.append(_pie_chart(sheet_id, "By risk level",
                               _rect(sheet_id, r + 1, r + 3, 6, 7), _rect(sheet_id, r + 1, r + 3, 7, 8), anchor_col=8))

    def fmt(rect, cell_format, fields):
        return {"repeatCell": {"range": rect, "cell": {"userEnteredFormat": cell_format}, "fields": fields}}

    # Title
    requests.append(fmt(_rect(sheet_id, 1, 1, 0, 1), {"textFormat": {"bold": True, "fontSize": 18}}, "userEnteredFormat.textFormat"))
    requests.append(fmt(_rect(sheet_id, 2, 2, 0, 1), {"textFormat": {"italic": True, "foregroundColor": {"red": 0.5, "green": 0.55, "blue": 0.55}}},
                        "userEnteredFormat.textFormat"))
    # KPI labels + values
    requests.append(fmt(_rect(sheet_id, 3, 3, 0, 9), {"backgroundColor": DARK, "horizontalAlignment": "CENTER", "wrapStrategy": "WRAP",
                                                      "textFormat": {"bold": True, "foregroundColor": WHITE, "fontSize": 9}},
                        "userEnteredFormat(backgroundColor,horizontalAlignment,wrapStrategy,textFormat)"))
    requests.append(fmt(_rect(sheet_id, 4, 4, 0, 9), {"backgroundColor": LIGHT, "horizontalAlignment": "CENTER",
                                                      "textFormat": {"bold": True, "fontSize": 16}},
                        "userEnteredFormat(backgroundColor,horizontalAlignment,textFormat)"))
    # Section labels
    for row, col in [(r - 1, 0), (r - 1, 3), (r - 1, 6), (r - 1, 9), (CHARTS_ANCHOR_ROW - 1, 0), (LATEST_LABEL_ROW, 0), (REVIEW_LABEL_ROW, 0)]:
        requests.append(fmt(_rect(sheet_id, row, row, col, col + 1), {"textFormat": {"bold": True, "fontSize": 12}}, "userEnteredFormat.textFormat"))
    # Table header rows
    for c0, c1 in [(0, 2), (3, 5), (6, 8), (9, 12)]:
        requests.append(fmt(_rect(sheet_id, r, r, c0, c1), {"backgroundColor": DARK, "textFormat": {"bold": True, "foregroundColor": WHITE}},
                            "userEnteredFormat(backgroundColor,textFormat)"))
    requests.append(fmt(_rect(sheet_id, LATEST_QUERY_ROW, LATEST_QUERY_ROW, 0, 8), {"backgroundColor": DARK, "textFormat": {"bold": True, "foregroundColor": WHITE}},
                        "userEnteredFormat(backgroundColor,textFormat)"))
    requests.append(fmt(_rect(sheet_id, REVIEW_QUERY_ROW, REVIEW_QUERY_ROW, 0, 7), {"backgroundColor": RED_BG, "textFormat": {"bold": True}},
                        "userEnteredFormat(backgroundColor,textFormat)"))
    # Date formats
    requests.append(fmt(_rect(sheet_id, r + 1, r + 12, 3, 4), {"numberFormat": {"type": "DATE", "pattern": "mmm yyyy"}}, "userEnteredFormat.numberFormat"))
    requests.append(fmt(_rect(sheet_id, LATEST_QUERY_ROW + 1, LATEST_QUERY_ROW + 15, 0, 1), {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}},
                        "userEnteredFormat.numberFormat"))
    requests.append(fmt(_rect(sheet_id, REVIEW_QUERY_ROW + 1, REVIEW_QUERY_ROW + 300, 0, 1), {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}},
                        "userEnteredFormat.numberFormat"))

    # Column widths: A..L
    for idx, px in enumerate([150, 130, 120, 160, 260, 130, 150, 140, 110, 110, 110, 110]):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": idx, "endIndex": idx + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize",
        }})
    requests.append({"updateSheetProperties": {
        "properties": {"sheetId": sheet_id, "gridProperties": {"hideGridlines": True}},
        "fields": "gridProperties.hideGridlines",
    }})

    # Conditional format: highlight High risk in the "Latest 15" Risk column (F).
    requests.append({"addConditionalFormatRule": {"index": 0, "rule": {
        "ranges": [_rect(sheet_id, LATEST_QUERY_ROW + 1, LATEST_QUERY_ROW + 15, 5, 6)],
        "booleanRule": {
            "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "High"}]},
            "format": {"backgroundColor": RED_BG, "textFormat": {"bold": True}},
        },
    }}})
    return requests


def main() -> int:
    reader = SheetsConfigReader()
    writer = DashboardWriter(reader)
    if not writer.enabled:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON and SHEET_ID must both be set (and valid).")
        return 1

    ss = writer._spreadsheet()

    # The tabs the formulas read from must exist first (they're created with
    # their headers if missing; existing data is never touched).
    writer.ensure_briefings_tab(ss)
    writer.ensure_health_tab(ss)

    import gspread

    try:
        ss.del_worksheet(ss.worksheet(DASHBOARD_TAB))
        print(f"Removed the old '{DASHBOARD_TAB}' tab.")
    except gspread.exceptions.WorksheetNotFound:
        pass

    ws = ss.add_worksheet(title=DASHBOARD_TAB, rows=400, cols=14, index=0)

    data = [{"range": addr, "values": [[val]]} for addr, val in _cells()]
    ws.batch_update(data, value_input_option="USER_ENTERED")

    ss.batch_update({"requests": build_requests(ws.id)})
    print(f"Built the '{DASHBOARD_TAB}' tab with {len(data)} cells and 3 charts.")
    print("It's the first tab. Open the Sheet to see it (it fills in as briefings are logged).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
