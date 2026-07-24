import hashlib
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from core.models import ContentQuality, NormalizedIssuance, RawIssuance
from core.parsing import clean_text


class BaseSourceAdapter(ABC):
    """Abstract Base Class (blueprint) for all regulatory website adapters."""

    @property
    @abstractmethod
    def regulator_id(self) -> str:
        """Returns the unique identifier for the regulator (e.g., 'BIR')."""
        pass

    @abstractmethod
    def fetch_latest_issuances(self, category_id: str, config: dict) -> List[RawIssuance]:
        """Scrapes or fetches raw issuances for a specific regulatory category."""
        pass

    def normalize(self, raw: RawIssuance) -> NormalizedIssuance:
        """Converts raw scraped data into a standardized object."""
        issuance_id = self._resolve_identifier(raw)
        quality, cleaned_text_content = self._assess_content_quality(raw.extracted_text)

        return NormalizedIssuance(
            issuance_id=issuance_id,
            regulator_id=raw.regulator_id,
            category_id=raw.category_id,
            title=clean_text(raw.title),
            canonical_url=raw.canonical_url.strip(),
            content_quality=quality,
            published_date_str=clean_text(raw.published_date_str) if raw.published_date_str else None,
            pdf_url=raw.pdf_url.strip() if raw.pdf_url else None,
            cleaned_text=cleaned_text_content,
        )

    def _resolve_identifier(self, raw: RawIssuance) -> str:
        """Guarantees a unique ID using a SHA256 hash fallback when official numbers are missing."""
        if raw.raw_identifier and raw.raw_identifier.strip():
            clean_id = clean_text(raw.raw_identifier)
            return f"{raw.regulator_id}_{clean_id}"

        payload = f"{clean_text(raw.title).lower()}|{raw.published_date_str or ''}|{raw.canonical_url.strip().lower()}"
        sha256_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"{raw.regulator_id}_HASH_{sha256_hash}"

    def _assess_content_quality(
        self, text: Optional[str]
    ) -> Tuple[ContentQuality, Optional[str]]:
        """Evaluates character density and length to flag empty or scanned image PDFs."""
        if not text or not text.strip():
            return ContentQuality.UNEXTRACTABLE_PDF, None

        cleaned = clean_text(text)

        if len(cleaned) < 150:
            return ContentQuality.LOW_QUALITY, cleaned

        alphanumeric_count = sum(1 for c in cleaned if c.isalnum())
        density = alphanumeric_count / len(cleaned)

        if density < 0.5:
            return ContentQuality.LOW_QUALITY, cleaned

        return ContentQuality.VALID, cleaned
