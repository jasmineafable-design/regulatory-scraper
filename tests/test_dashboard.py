from unittest.mock import MagicMock, patch

import gspread

import main as pipeline
from core.dashboard import BRIEFINGS_HEADERS, DashboardWriter, _text
from models.issuance import BriefingRecord, CandidateIssuance


def _briefing(identifier="RMC No. 1-2026", regulator="BIR", category="RMC", risk="High", **kw):
    return BriefingRecord(
        issuance_identifier=identifier,
        source_regulator=regulator,
        source_category=category,
        issuance_title=f"{identifier} - Test",
        official_source_link="https://www.bir.gov.ph/test",
        executive_summary="A summary.",
        risk_priority_level=risk,
        attachment_filename="BIR_RMC_RMC-No-1-2026.pdf",
        completeness_status="complete",
        **kw,
    )


class FakeWorksheet:
    def __init__(self, existing_rows=None):
        self.rows = [list(BRIEFINGS_HEADERS)] + (existing_rows or [])
        self.appended = []
        self.cleared = False
        self.updated = None

    def col_values(self, col):
        return [r[col - 1] if len(r) >= col else "" for r in self.rows]

    def append_rows(self, rows, **kwargs):
        self.appended.extend(rows)
        self.rows.extend(rows)

    def clear(self):
        self.cleared = True

    def update(self, values=None, range_name=None, **kwargs):
        self.updated = values

    def freeze(self, **kw): pass
    def format(self, *a, **kw): pass
    def set_basic_filter(self, *a, **kw): pass


class FakeSpreadsheet:
    def __init__(self, tabs=None):
        self.tabs = tabs or {}

    def worksheet(self, title):
        if title not in self.tabs:
            raise gspread.exceptions.WorksheetNotFound(title)
        return self.tabs[title]

    def add_worksheet(self, title, rows, cols, index=None):
        self.tabs[title] = FakeWorksheet()
        return self.tabs[title]


def _writer(spreadsheet):
    reader = MagicMock()
    reader._gc = MagicMock()
    reader._gc.open_by_key.return_value = spreadsheet
    reader.spreadsheet_id = "sheet123"
    return DashboardWriter(reader)


def test_disabled_without_a_real_sheet():
    reader = MagicMock()  # spreadsheet_id is a MagicMock, not a string id
    assert DashboardWriter(reader).enabled is False
    assert DashboardWriter(None).enabled is False


def test_disabled_by_env_var(monkeypatch):
    monkeypatch.setenv("DASHBOARD_DISABLED", "1")
    assert _writer(FakeSpreadsheet()).enabled is False


def test_log_briefings_appends_a_row_with_the_standard_columns():
    ss = FakeSpreadsheet({"Briefings": FakeWorksheet()})
    writer = _writer(ss)

    added = writer.log_briefings([_briefing(), _briefing("CL 2026-05", "IC", "IC-CL", risk="Low")])

    assert added == 2
    row_bir, row_ic = ss.tabs["Briefings"].appended
    assert len(row_bir) == len(BRIEFINGS_HEADERS)
    assert row_bir[1:4] == ["BIR", "RMC", "RMC No. 1-2026"]
    assert row_bir[5:7] == ["High", "Yes"]           # High risk -> needs review
    assert row_ic[1:3] == ["IC", "CL"]               # regulator prefix stripped from type
    assert row_ic[5:7] == ["Low", "No"]
    assert row_bir[11] == "BIR_RMC_RMC-No-1-2026.pdf"
    assert row_bir[12] == "https://www.bir.gov.ph/test"


def test_archived_copy_column_holds_the_drive_link_when_there_is_one():
    ss = FakeSpreadsheet({"Briefings": FakeWorksheet()})
    writer = _writer(ss)
    link = "https://drive.google.com/file/d/abc/view"
    b = _briefing(archived_document_link=link)
    b.attachment_filename = None

    writer.log_briefings([b])

    assert ss.tabs["Briefings"].appended[0][11] == link


def test_log_briefings_creates_missing_tab_with_headers():
    ss = FakeSpreadsheet()
    writer = _writer(ss)

    writer.log_briefings([_briefing()])

    assert "Briefings" in ss.tabs
    assert ss.tabs["Briefings"].updated == [BRIEFINGS_HEADERS]


def test_log_briefings_skips_ones_already_logged():
    """A re-sent briefing (duplicate notification is acceptable per the
    architecture) must not double-count on the dashboard."""
    existing = [["2026-10-01", "BIR", "RMC", "RMC No. 1-2026"]]
    ss = FakeSpreadsheet({"Briefings": FakeWorksheet(existing_rows=existing)})
    writer = _writer(ss)

    added = writer.log_briefings([_briefing("RMC No. 1-2026"), _briefing("RMC No. 2-2026")])

    assert added == 1
    assert ss.tabs["Briefings"].appended[0][3] == "RMC No. 2-2026"


def test_log_briefings_never_raises_when_sheet_fails():
    reader = MagicMock()
    reader._gc = MagicMock()
    reader._gc.open_by_key.side_effect = RuntimeError("403 caller does not have permission")
    reader.spreadsheet_id = "sheet123"

    assert DashboardWriter(reader).log_briefings([_briefing()]) == 0


def test_text_neutralises_formula_triggers_and_truncates():
    assert _text("=HYPERLINK('x')") == "'=HYPERLINK('x')"
    assert _text("-5 days") == "'-5 days"
    assert _text("normal") == "normal"
    assert len(_text("x" * 5000)) <= 2000


def test_health_snapshot_overwrites_with_latest_run_only():
    ss = FakeSpreadsheet()
    writer = _writer(ss)

    ok = writer.write_health_snapshot(
        is_opening_check=True, total_new=2, notified=2,
        source_status=[("BIR/RMC", "OK", "40 fetched, 2 new"), ("IC/IC-CL", "FAILED", "403")],
    )

    assert ok is True
    ws = ss.tabs["Health"]
    assert ws.cleared is True
    grid = ws.updated
    assert grid[1] == ["Run type", "Opening check"]
    assert grid[4] == ["Result", "1 source(s) failed"]
    assert grid[6] == ["Source", "Status", "Detail"]   # header row the Dashboard formulas expect (row 7)
    assert grid[7] == ["BIR/RMC", "OK", "40 fetched, 2 new"]
    assert grid[8][1] == "FAILED"


def test_health_snapshot_never_raises():
    reader = MagicMock()
    reader._gc = MagicMock()
    reader._gc.open_by_key.side_effect = RuntimeError("boom")
    reader.spreadsheet_id = "sheet123"

    assert DashboardWriter(reader).write_health_snapshot(False, 0, 0, []) is False


def test_run_logs_notified_briefings_and_health_after_notification(tmp_path):
    adapter = MagicMock()
    adapter.regulator_id = "BIR"
    adapter.category = "RMC"
    adapter.OPENING_CHECK_ONLY = False
    adapter.fetch_latest_issuances.return_value = [
        CandidateIssuance("BIR", "RMC", "RMC No. 9-2026", "t", "https://x.test", "raw")
    ]
    reader = MagicMock()
    reader.get_active_sources.return_value = None
    reader.get_recipient_matrix.return_value = {}

    state = pipeline.StateManager(filepath=str(tmp_path / "state.json"))
    state.mark_seen("RMC No. 1-2026", "BIR", "old", status="BASELINE", category="RMC")  # category already baselined

    fake_dashboard = MagicMock()
    with patch.object(pipeline, "ADAPTERS", [adapter]), \
         patch.object(pipeline, "DashboardWriter", return_value=fake_dashboard), \
         patch.object(pipeline, "build_notification_channel", lambda m: pipeline.ConsoleNotificationChannel()):
        pipeline.run(is_opening_check=True, state_manager=state, config_reader=reader)

    logged = fake_dashboard.log_briefings.call_args.args[0]
    assert [b.issuance_identifier for b in logged] == ["RMC No. 9-2026"]
    health_args = fake_dashboard.write_health_snapshot.call_args.args
    assert health_args[0] is True and health_args[1] == 1 and health_args[2] == 1
    assert health_args[3][0][:2] == ("BIR/RMC", "OK")


def test_run_writes_health_even_when_an_adapter_fails(tmp_path):
    adapter = MagicMock()
    adapter.regulator_id = "IC"
    adapter.category = "IC-CL"
    adapter.OPENING_CHECK_ONLY = False
    adapter.fetch_latest_issuances.side_effect = RuntimeError("403 blocked")
    reader = MagicMock()
    reader.get_active_sources.return_value = None
    reader.get_recipient_matrix.return_value = {}

    fake_dashboard = MagicMock()
    with patch.object(pipeline, "ADAPTERS", [adapter]), \
         patch.object(pipeline, "DashboardWriter", return_value=fake_dashboard), \
         patch.object(pipeline, "build_notification_channel", lambda m: pipeline.ConsoleNotificationChannel()):
        try:
            pipeline.run(is_opening_check=True, state_manager=pipeline.StateManager(filepath=str(tmp_path / "s.json")),
                         config_reader=reader)
        except RuntimeError:
            pass  # fail-loud re-raise is expected and unchanged

    status = fake_dashboard.write_health_snapshot.call_args.args[3]
    assert status[0][:2] == ("IC/IC-CL", "FAILED")


def test_setup_dashboard_cells_and_requests_are_well_formed():
    import re
    from tools import setup_dashboard as sd

    cells = sd._cells()
    addrs = [a for a, _ in cells]
    assert len(addrs) == len(set(addrs)), "duplicate cell address in the Dashboard layout"
    assert all(re.fullmatch(r"[A-Z]+\d+", a) for a in addrs)

    formulas = [v for _, v in cells if isinstance(v, str) and v.startswith("=")]
    assert formulas
    for f in formulas:
        assert f.count("(") == f.count(")"), f
        assert f.count("{") == f.count("}"), f
    assert any("Health!B5" in f for f in formulas)

    requests = sd.build_requests(sheet_id=42)
    assert not [r for r in requests if "addChart" in r], "the redesign has no charts"
    assert all("sheetId" in str(r) for r in requests)


def test_dashboard_cards_match_the_agreed_definitions():
    from tools import setup_dashboard as sd

    cells = dict(sd._cells())
    labels = [cells[f"{c}4"] for c in "ABCDE"]
    assert labels == ["For Assessment", "Applicable / Open", "High-Risk Open", "Overdue", "Due Soon (30 days)"]
    # Cards read the team columns: O=Applicability, S=Due Date, T=Status; F=Review Priority.
    assert 'Briefings!O2:O,"")' in cells["A5"]                 # unassessed = no applicability yet
    for card in ("B5", "C5", "D5", "E5"):
        assert '{"Yes","Partially"}' in cells[card]             # open needs Yes/Partially
        assert '{"Closed","Not Applicable"}' in cells[card]     # ...and not Closed/Not Applicable
    assert 'Briefings!F2:F="High"' in cells["C5"]
    assert "TODAY()+30" in cells["E5"]
    # The Action Required table: 7 visible columns, overdue first, capped at 20.
    action = cells["A9"]
    assert "ARRAY_CONSTRAIN(SORT(picked,8,TRUE),20,7)" in action
    # Row-by-row names must be array-wrapped (LET alone gives no array context).
    for name in ("here", "isOpen", "isNew", "late", "high", "sortKey", "shownStatus"):
        assert f"{name},ARRAYFORMULA(" in action, name
    # A failure must not read as an all-clear: the fallback checks the cards.
    assert 'IF(A5+B5=0,"Nothing needs attention right now"' in action
    assert "Table could not load" in action
    assert [cells[f"{c}8"] for c in "ABCDEFG"] == ["Priority", "Regulator", "Issuance No.", "Owner", "Due Date", "Status", "Title"]


def test_demo_rows_cover_every_card_and_match_the_briefings_layout():
    from tools import setup_dashboard as sd
    from core.dashboard import BRIEFINGS_HEADERS

    rows = sd.demo_rows()
    assert all(len(r) == len(BRIEFINGS_HEADERS) for r in rows)
    assert all(r[1] == "DEMO" for r in rows), "demo rows must be findable for removal"
    idx = {h: i for i, h in enumerate(BRIEFINGS_HEADERS)}
    applic = [r[idx["Applicability"]] for r in rows]
    assert {"", "Yes", "No", "Partially"} <= set(applic)
    statuses = {r[idx["Status"]] for r in rows}
    assert {"For Assessment", "Closed", "Not Applicable"} <= statuses


def test_dashboard_has_archive_link_only_when_configured(monkeypatch):
    from tools import setup_dashboard as sd

    monkeypatch.setenv("ARCHIVE_FOLDER_URL", "https://drive.google.com/drive/folders/ABC123")
    cells = dict(sd._cells())
    assert cells["F32"] == '=HYPERLINK("https://drive.google.com/drive/folders/ABC123","Open the Regulatory Archive")'

    monkeypatch.setenv("ARCHIVE_FOLDER_URL", "")
    assert "F32" not in dict(sd._cells())


# --- Briefings layout: scraper columns + team columns, 2026-10-07 ----------


def test_briefings_headers_split_scraper_and_team_columns():
    assert len(BRIEFINGS_HEADERS) == 20
    assert BRIEFINGS_HEADERS[5] == "Review Priority"          # renamed from Risk/Priority
    assert BRIEFINGS_HEADERS[14:] == ["Applicability", "Impact/Risk", "Required Action", "Owner", "Due Date", "Status"]


def test_new_rows_start_for_assessment_and_leave_team_columns_blank():
    ss = FakeSpreadsheet({"Briefings": FakeWorksheet()})
    _writer(ss).log_briefings([_briefing()])

    row = ss.tabs["Briefings"].appended[0]
    assert len(row) == 20
    assert row[14:19] == ["", "", "", "", ""]     # Applicability..Due Date: the team fills these in
    assert row[19] == "For Assessment"            # Status


def test_pipeline_never_overwrites_team_entries_on_existing_rows():
    """Existing rows are only ever read (to dedupe); new briefings are
    appended. The team's O..T entries on earlier rows must be untouched."""
    team_row = ["2026-10-01", "BIR", "RMC", "RMC No. 1-2026"] + [""] * 10 + ["Yes", "", "File", "Maria", "2026-11-01", "In Progress"]
    ws = FakeWorksheet(existing_rows=[team_row])
    ws.update = MagicMock()
    ws.clear = MagicMock()
    ws.batch_update = MagicMock()
    ss = FakeSpreadsheet({"Briefings": ws})

    _writer(ss).log_briefings([_briefing("RMC No. 1-2026"), _briefing("RMC No. 2-2026")])

    assert ws.rows[1] == team_row                  # unchanged
    ws.update.assert_not_called()
    ws.clear.assert_not_called()
    ws.batch_update.assert_not_called()


def test_briefings_format_has_dropdowns_hidden_legacy_column_and_team_header_colour():
    from core.dashboard import APPLICABILITY_OPTIONS, STATUS_OPTIONS, briefings_format_requests

    reqs = briefings_format_requests(sheet_id=9)
    validations = [r["setDataValidation"] for r in reqs if "setDataValidation" in r]
    by_col = {v["range"]["startColumnIndex"]: v["rule"]["condition"] for v in validations}

    assert [x["userEnteredValue"] for x in by_col[14]["values"]] == APPLICABILITY_OPTIONS   # O
    assert [x["userEnteredValue"] for x in by_col[19]["values"]] == STATUS_OPTIONS          # T
    assert by_col[18]["type"] == "DATE_IS_VALID"                                            # S
    # Dropdown ranges are unbounded downward, so rows appended later get them too.
    assert all("endRowIndex" not in v["range"] for v in validations)
    hidden = [r for r in reqs if r.get("updateDimensionProperties", {}).get("properties", {}).get("hiddenByUser")]
    assert hidden and hidden[0]["updateDimensionProperties"]["range"]["startIndex"] == 6   # G, legacy Needs Review


def test_upgrade_briefings_tab_rewrites_only_the_header_row():
    ws = FakeWorksheet(existing_rows=[["2026-10-01", "BIR", "RMC", "RMC No. 1-2026"]])
    ws.col_count = 14
    ws.resize = MagicMock()
    ws.update = MagicMock()
    ss = FakeSpreadsheet({"Briefings": ws})
    ss.batch_update = MagicMock()

    _writer(ss).upgrade_briefings_tab(ss)

    ws.resize.assert_called_once_with(cols=20)
    (call,) = ws.update.call_args_list
    assert call.kwargs["range_name"] == "A1" and call.kwargs["values"] == [BRIEFINGS_HEADERS]
    assert ws.rows[1] == ["2026-10-01", "BIR", "RMC", "RMC No. 1-2026"]   # data untouched
