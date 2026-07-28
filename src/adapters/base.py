from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseAdapter(ABC):
    """
    Abstract Base Adapter defining the standard interface for regulator-specific
    source adapters under Architecture Pattern 3.
    """

    @abstractmethod
    def fetch(() -> str:
        """
        Fetches raw content (HTML/JSON/PDF payload) from the regulator source.
        Raises an exception if the fetch fails completely.
        """
        pass

    @abstractmethod
    def validate(self, raw_content: str) -> bool:
        """
        Validates whether the raw content meets basic expected DOM/structural standards.
        Returns False if the page structure is invalid, incomplete, or corrupted.
        """
        pass

    @abstractmethod
    def parse(self, raw_content: str) -> List[Dict[str, Any]]:
        """
        Parses raw content into candidate issuance data objects matching the core contract.
        """
        pass
