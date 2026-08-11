from abc import ABC, abstractmethod
from typing import List

from models.issuance import CandidateIssuance


class BaseAdapter(ABC):
    """
    Abstract Base Class that all regulator source adapters (BIR, IC, SEC) must inherit
    from. Enforces the adapter contract from Handoff §4.1: each adapter owns Fetch and
    Validate for its own regulator, and normalizes output into the shared
    models.issuance.CandidateIssuance model. Adapters never call each other and never
    call into the Shared Core directly.
    """

    @property
    @abstractmethod
    def regulator_id(self) -> str:
        """Returns the unique identifier for the regulator (e.g., 'BIR', 'IC', 'SEC')."""
        raise NotImplementedError

    @abstractmethod
    def fetch_latest_issuances(self) -> List[CandidateIssuance]:
        """
        Fetches from the official source (directly, or through a sanctioned access
        path), validates that the response is genuine, and returns standardized
        CandidateIssuance objects (§5.1). A fetch or validation failure must be raised,
        never silently converted into an empty list.
        """
        raise NotImplementedError
