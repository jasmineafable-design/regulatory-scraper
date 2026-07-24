from core.config import SystemConfig, DEFAULT_SCRAPER_TARGETS
from core.google_sheets import GoogleSheetsConfigFetcher


def test_system_config_fallback():
    """Ensures fallback defaults are loaded when no Google Sheet URL is provided."""
    config = SystemConfig.load()
    assert len(config.targets) > 0
    assert config.targets[0].regulator_id == "BIR"


def test_google_sheets_fetcher_invalid_url():
    """Ensures Google Sheets fetcher gracefully handles invalid URLs without crashing."""
    rows = GoogleSheetsConfigFetcher.fetch_csv_as_dicts("https://invalid-url-example.com/fake.csv")
    assert rows == []
