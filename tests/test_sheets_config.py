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
