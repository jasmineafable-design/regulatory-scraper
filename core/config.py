import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    """Central configuration settings for the regulatory scraper system."""

    STATE_FILE_PATH: str = field(
        default_factory=lambda: os.getenv("STATE_FILE_PATH", "state/seen_issuances.json")
    )
    SLACK_WEBHOOK_URL: str | None = field(
        default_factory=lambda: os.getenv("SLACK_WEBHOOK_URL")
    )


# Exported global instance
settings = Settings()
