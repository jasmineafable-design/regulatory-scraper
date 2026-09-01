import json
from unittest.mock import MagicMock, patch

from core.sheets_config import SheetsConfigReader


def _unconfigured_reader() -> SheetsConfigReader:
    """A reader with no service account/spreadsheet ID -- exercises the
    fail-open, no-Sheet-configured path without touching the network."""
    return SheetsConfigReader(service_account_json=None, spreadsheet_id=None)


def test_get_active_sources_returns_none_when_unconfigured():
    reader = _unconfigured_reader()
    assert reader.get_active_sources() is None


def test_get_recipient_matrix_empty_when_unconfigured():
    reader = _unconfigured_reader()
    assert reader.get_recipient_matrix() == {}


def test_get_schedule_config_returns_documented_defaults_when_unconfigured():
    reader = _unconfigured_reader()
    config = reader.get_schedule_config()
    assert config["BusinessDays"] == "Mon,Tue,Wed,Thu,Fri"
    assert config["OpeningTime"] == "10:00"
    assert config["PollingIntervalMinutes"] == "30"


def test_get_active_sources_filters_by_active_flag(monkeypatch):
    reader = _unconfigured_reader()
    monkeypatch.setattr(
        reader,
        "get_sources_config",
        lambda: [
            {"Regulator": "bir", "Category": "rmc", "Active": "Y", "Recipients": "a@x.com"},
            {"Regulator": "ic", "Category": "ic-cl", "Active": "N", "Recipients": "b@x.com"},
            {"Regulator": "sec", "Category": "sec-mc", "Active": "yes", "Recipients": "c@x.com"},
        ],
    )
    active = reader.get_active_sources()
    assert active == {("BIR", "RMC"), ("SEC", "SEC-MC")}


def test_authenticates_from_raw_json_secret_content():
    # Regression test: GOOGLE_SERVICE_ACCOUNT_JSON is documented as "paste
    # the entire contents of the downloaded JSON key file" into the GitHub
    # secret -- i.e. raw JSON text, not a path to a file on disk. Passing
    # that text to gspread.service_account(filename=...) fails with
    # "File name too long" since gspread tries to open a file whose name is
    # the whole JSON blob. This must go through service_account_from_dict
    # instead, keyed off successfully parsing the string as JSON.
    fake_creds = {"type": "service_account", "client_email": "x@y.iam.gserviceaccount.com"}
    mock_gspread = MagicMock()

    with patch.dict("sys.modules", {"gspread": mock_gspread}):
        SheetsConfigReader(service_account_json=json.dumps(fake_creds), spreadsheet_id="sheet-123")

    mock_gspread.service_account_from_dict.assert_called_once_with(fake_creds)
    mock_gspread.service_account.assert_not_called()


def test_falls_back_to_file_path_when_secret_is_not_json():
    mock_gspread = MagicMock()

    with patch.dict("sys.modules", {"gspread": mock_gspread}):
        SheetsConfigReader(service_account_json="/some/local/key.json", spreadsheet_id="sheet-123")

    mock_gspread.service_account.assert_called_once_with(filename="/some/local/key.json")
    mock_gspread.service_account_from_dict.assert_not_called()


def test_get_recipient_matrix_keys_by_regulator_and_category(monkeypatch):
    reader = _unconfigured_reader()
    monkeypatch.setattr(
        reader,
        "get_sources_config",
        lambda: [
            {"Regulator": "IC", "Category": "IC-CL", "Recipients": "compliance@x.com"},
            {"Regulator": "IC", "Category": "IC-ADVISORY", "Recipients": "legal@x.com"},
        ],
    )
    matrix = reader.get_recipient_matrix()
    assert matrix[("IC", "IC-CL")] == ["compliance@x.com"]
    assert matrix[("IC", "IC-ADVISORY")] == ["legal@x.com"]
