import logging
from typing import List, Dict, Any
import requests
from bs4 import BeautifulSoup
from src.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)

class SECAdapter(BaseAdapter):
    """
    Adapter for scraping Securities and Exchange Commission (SEC) issuances.
    """

    BASE_URL = "https://www.sec.gov.ph"

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def fetch(self) -> List[Dict[str, Any]]:
        """
        Fetches latest memorandum circulars and opinions from SEC.
        """
        items: List[Dict[str, Any]] = []
        try:
            response = requests.get(f"{self.BASE_URL}/mc-2026/", headers=self.headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                for row in soup.find_all("tr"):
                    cols = row.find_all("td")
                    if len(cols) >= 2:
                        link = row.find("a")
                        items.append({
                            "title": cols[0].get_text(strip=True),
                            "url": link.get("href") if link else "",
                            "regulator": "SEC",
                            "raw_payload": str(row)
                        })
        except Exception as e:
            logger.error(f"SECAdapter fetch failed: {str(e)}")
            raise e

        return items
