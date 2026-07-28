from abc import ABC, abstractmethod
from typing import List
from core.models import CandidateIssuance


class BaseAdapter(ABC):
    """
    Abstract Base Class that all source adapters (BIR, IC, SEC) must inherit from.
    Enforces a standardized interface across all regulatory scrapers.
    """

    @property
    @abstractmethod
    def regulator_id(self) -> str:
        """
        Returns the unique identifier for the regulator (e.g., 'BIR', 'IC', 'SEC').
        """
        pass

    @abstractmethod
    def fetch_latest_issuances(self) -> List[CandidateIssuance]:
        """
        Scrapes or fetches the latest regulatory updates from the official source,
        validates the output, and returns a list of standardized CandidateIssuance objects.
        """
        pass
