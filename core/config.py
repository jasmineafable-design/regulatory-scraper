import os
from dataclasses import dataclass


@dataclass
class Settings:
    """System-wide configuration settings loaded from environment variables."""

    STATE_FILE_PATH: str = os.getenv("STATE_FILE_PATH", "state/seen_issuances.json")
    SLACK_WEBHOOK_URL: str | None = os.getenv("SLACK_WEBHOOK_URL")


# Global configuration instance exported for application use
settings = Settings()
