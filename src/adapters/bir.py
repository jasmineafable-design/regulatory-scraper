import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from src.adapters.base import BaseAdapter


class BIRAdapter(BaseAdapter):
    """
    Regulator Source Adapter for the Bureau of Internal Revenue (BIR).
    """

    DEFAULT_URL = "https://www.bir.gov.ph/index.php/revenue-issuances/revenue-memorandum-circulars.html"

    def __init__(self, target_url: str = None, timeout: int = 15):
        self.target_url = target_url or self.DEFAULT_URL
        self.timeout = timeout

    def fetch(self) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(self.target_url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def validate(self, raw_content: str) -> bool:
        if not raw_content or not raw_content.strip():
            return False
        
        soup = BeautifulSoup(raw_content, "html.parser")
        # Validate that table container exists in raw content
        table = soup.find("table")
        return table is not None

    def parse(self, raw_content: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(raw_content, "html.parser")
        candidates = []

        table = soup.find("table")
        if not table:
            return candidates

        rows = table.find_all("tr")
        if not rows:
            return candidates

        # Skip table header row
        for row in rows[1:]:
            cols = row.find_all(["td", "th"])
            if len(cols) < 2:
                continue

            issuance_no = cols[0].get_text(strip=True)
            title_col = cols[1]
            date_str = cols[2].get_text(strip=True) if len(cols) > 2 else ""

            link_tag = title_col.find("a")
            pdf_url = link_tag["href"] if link_tag and link_tag.has_attr("href") else ""
            title_text = title_col.get_text(strip=True)

            if issuance_no and title_text:
                candidates.append({
                    "regulator": "BIR",
                    "issuance_number": issuance_no,
                    "title": title_text,
                    "issue_date": date_str,
                    "source_url": pdf_url,
                    "category": "RMC"
                })

        return candidates
