import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load local .env file if present
load_dotenv()


@dataclass(frozen=True)
class ApplicationConfig:
    """Holds core application environment settings."""
    environment: str
    log_level: str

    @classmethod
    def load_from_env(cls) -> "ApplicationConfig":
        """Reads configuration settings from system environment variables."""
        return cls(
            environment=os.getenv("APP_ENV", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
