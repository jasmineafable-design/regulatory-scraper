class RegulatoryScraperError(Exception):
    """Base exception class for all regulatory scraper errors."""
    pass


class AdapterFetchError(RegulatoryScraperError):
    """Raised when an adapter fails to fetch HTML/content from a target regulator website."""
    def __init__(self, regulator_id: str, url: str, original_error: Exception):
        self.regulator_id = regulator_id
        self.url = url
        self.original_error = original_error
        super().__init__(f"[{regulator_id}] Failed to fetch URL '{url}': {original_error}")


class ParsingError(RegulatoryScraperError):
    """Raised when an adapter fails to parse structure/data from retrieved web content."""
    def __init__(self, regulator_id: str, details: str):
        self.regulator_id = regulator_id
        self.details = details
        super().__init__(f"[{regulator_id}] Parsing failure: {details}")
