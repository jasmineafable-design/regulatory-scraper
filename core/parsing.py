import re
from typing import Optional
from urllib.parse import urljoin, urlparse
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


def fallback_identifier(title: str, href: str = "", max_title_chars: int = 40) -> str:
    """Builds a *unique* identifier for an issuance whose title contains no
    parseable issuance number.

    A bare title truncation is not safe as a state key: regulator titles
    routinely share a long common prefix ("Notice to All Insurance Companies
    Regarding ..."), so two distinct issuances collapse to the same
    identifier and the second is silently swallowed as already-seen.
    Appending the URL's last path segment disambiguates them, since each
    issuance has its own page.
    """
    stem = clean_text(title)[:max_title_chars].strip()
    slug = ""
    if href:
        slug = urlparse(href.strip()).path.rstrip("/").rsplit("/", 1)[-1]
    return f"{stem} [{slug}]" if slug else stem


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
