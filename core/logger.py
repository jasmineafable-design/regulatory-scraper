import logging
import sys
from pathlib import Path

# Ensure logs directory exists
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"


def setup_logger(name: str = "regulatory_scraper") -> logging.Logger:
    """Creates and configures a standardized logger instance.

    Console logs output human-friendly text.
    File logs append persistent operational records for troubleshooting.
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers if setup_logger is called multiple times
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.INFO)

    # Log format: Time | Level | Component Name | Message
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler 1: Terminal/Console Output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Handler 2: Log File Storage
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
