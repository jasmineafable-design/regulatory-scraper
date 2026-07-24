import csv
import io
import requests
from typing import List, Dict, Any
from core.logger import setup_logger

logger = setup_logger("google_sheets")


class GoogleSheetsConfigFetcher:
    """Fetches configuration tables directly from published Google Sheets CSV links."""

    @staticmethod
    def fetch_csv_as_dicts(csv_url: str) -> List[Dict[str, str]]:
        """Downloads a public/published Google Sheet CSV tab and returns rows as dictionaries."""
        if not csv_url or not csv_url.strip():
            logger.warning("Empty Google Sheets CSV URL provided.")
            return []

        try:
            response = requests.get(csv_url.strip(), timeout=10)
            response.raise_for_status()

            # Parse CSV content from response text
            csv_file = io.StringIO(response.text)
            reader = csv.DictReader(csv_file)
            rows = [row for row in reader]

            logger.info(f"Successfully fetched {len(rows)} records from Google Sheets.")
            return rows

        except Exception as e:
            logger.error(f"Failed to fetch Google Sheets configuration from URL: {e}")
            return []
