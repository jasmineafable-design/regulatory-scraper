import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    """Central configuration settings for the regulatory scraper system."""

    STATE_FILE_PATH: str = field(
        default_factory=lambda: os.getenv("STATE_FILE_PATH", "state/seen_issuances.json")
    )
    # No Slack/webhook setting here: the frozen Foundation describes email
    # (SMTP/Gmail) as the only approved notification channel. A Slack webhook
    # channel existed in the pre-consolidation code (core/notifier.py) but was
    # never part of the approved architecture — see the consolidation summary.


# Exported global instance
settings = Settings()
