from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseAdapter(ABC):
    """
    Abstract Base Class for all regulatory adapters.
    Serves as the interface enforcing consistent retrieval across regulators.
    """

    @abstractmethod
    def fetch(self) -> List[Dict[str, Any]]:
        """
        Fetches regulatory items from the source.
        Returns a list of raw items structured as dictionaries.
        """
        pass
