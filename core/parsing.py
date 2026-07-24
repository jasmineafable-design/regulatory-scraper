import re
from typing import Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup


def clean_text(text: Optional[str]) -> str:
    """Strips extra whitespace, tabs, and newlines into a single clean line."""
    if not text:
        return ""
    # Collapse multiple whitespace characters into one
    return re.sub(r"\s+", " ", text).strip()


def make_absolute_url(base_url: str, relative_or_absolute_url: str) -> str:
    """Converts relative URLs (e.g. '/downloads/doc.pdf') into absolute web URLs."""
    if not relative_or_absolute_url:
        return ""
    return urljoin(base_url, relative_or_absolute_url.strip())


def extract_html_text(html_content: str) -> str:
    """Extracts clean plain text from raw HTML content."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove script and style blocks
    for script in soup(["script", "style", "header", "footer", "nav"]):
        script.extract()
        
    raw_text = soup.get_text(separator=" ")
    return clean_text(raw_text)
