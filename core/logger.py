import logging
import sys
from pathlib import Path

# Ensure logs directory exists
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"


def _formatter() -> logging.Formatter:
    # Log format: Time | Level | Component Name | Message
    return logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def configure_root_logging() -> None:
    """Attaches the standard console+file handlers to the ROOT logger.

    Most modules here declare `logger = logging.getLogger(__name__)` rather
    than calling setup_logger. Those loggers have no handlers of their own and
    the root logger had none either, so their records were silently discarded
    -- which is why a successful IC/SEC fetch logged its 'Fetching URL' line
    (http_client uses setup_logger) but never its
    '[IC] Extracted N candidate(s)' line (ic_adapter does not). Successes were
    therefore indistinguishable from silence in the run log, and only failures
    were legible. Configuring the root logger makes every module's output
    appear without touching each module.
    """
    root = logging.getLogger()
    if any(getattr(h, "_regulatory_scraper", False) for h in root.handlers):
        return

    root.setLevel(logging.INFO)
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE, encoding="utf-8")):
        handler.setFormatter(_formatter())
        handler._regulatory_scraper = True
        root.addHandler(handler)


def setup_logger(name: str = "regulatory_scraper") -> logging.Logger:
    """Creates and configures a standardized logger instance.

    Console logs output human-friendly text.
    File logs append persistent operational records for troubleshooting.

    Handlers now live on the root logger (see configure_root_logging), so this
    returns a plain named logger whose records propagate up to them. Attaching
    a second set of handlers here would print every line twice.
    """
    configure_root_logging()
    return logging.getLogger(name)
