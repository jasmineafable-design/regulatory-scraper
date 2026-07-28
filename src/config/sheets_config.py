import logging
from typing import Dict, Any
import gspread

logger = logging.getLogger(__name__)

class SheetsConfigReader:
    """
    Reads operational and context configurations managed by business users via Google Sheets.
    """

    def __init__(self, service_account_json: str, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        try:
            self.gc = gspread.service_account(filename=service_account_json)
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Sheets API: {str(e)}")
            raise e

    def get_operational_config(self) -> Dict[str, Any]:
        """
        Retrieves active flags, scraping timeouts, and execution parameters.
        """
        sheet = self.gc.open_by_key(self.spreadsheet_id).worksheet("OperationalConfig")
        records = sheet.get_all_records()
        return {row["Key"]: row["Value"] for row in records if "Key" in row}

    def get_recipient_matrix(self) -> Dict[str, Any]:
        """
        Retrieves notification mapping rules per regulator / impact assessment level.
        """
        sheet = self.gc.open_by_key(self.spreadsheet_id).worksheet("RecipientMatrix")
        return sheet.get_all_records()
