import logging
from typing import List, Dict, Any
import requests
from bs4 import BeautifulSoup
from src.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)

class ICAdapter(BaseAdapter):
    """
    Adapter for scraping Insurance Commission (IC) circulars and advisories.
    """
    
    BASE_URL = "https://www.insurance.gov.ph"

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def fetch(self) -> List[Dict[str, Any]]:
        """
        Fetches latest issuances from IC.
        """
        items: List[Dict[str, Any]] = []
        try:
            # Operational fetch logic will query the target section page
            response = requests.get(f"{self.BASE_URL}/category/circular-letters/", headers=self.headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                # Parse listings matching the page structure
                for article in soup.find_all("article"):
                    title_elem = article.find("h2") or article.find("a")
                    if title_elem:
                        items.append({
                            "title": title_elem.get_text(strip=True),
                            "url": title_elem.get("href", ""),
                            "regulator": "IC",
                            "raw_payload": str(article)
                        })
        except Exception as e:
            logger.error(f"ICAdapter fetch failed: {str(e)}")
            # Enforce "fail-loud" or log accordingly based on config
            raise e

        return items
