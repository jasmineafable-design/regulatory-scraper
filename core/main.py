from core.config import ApplicationConfig
from core.logger import setup_logger

logger = setup_logger("main")


def main() -> None:
    """Primary system entry point."""
    logger.info("Initializing Regulatory Scraper System...")

    config = ApplicationConfig.load_from_env()
    logger.info(f"Environment initialized: {config.environment}")
    logger.info("Phase 1 scaffolding active and operational.")


if __name__ == "__main__":
    main()
