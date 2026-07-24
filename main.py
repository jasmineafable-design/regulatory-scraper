from core.config import SystemConfig
from core.logger import setup_logger
from core.parsing import clean_text, make_absolute_url, extract_html_text

logger = setup_logger("main")


def main() -> None:
    """Primary system entry point."""
    logger.info("Initializing Regulatory Scraper System...")

    # Load System Config
    config = SystemConfig.load()
    logger.info(f"System Environment: {config.environment}")

    # Demonstrate Shared Parsing Utilities
    sample_dirty_title = "  Revenue   Memorandum Circular \n No. 10-2026   "
    cleaned = clean_text(sample_dirty_title)
    logger.info(f"Cleaned Title Utility Demo: '{sample_dirty_title}' -> '{cleaned}'")

    relative_pdf = "/images/pb/RMC%20No.%2010-2026.pdf"
    base_domain = "https://www.bir.gov.ph"
    abs_url = make_absolute_url(base_domain, relative_pdf)
    logger.info(f"Absolute URL Utility Demo: '{relative_pdf}' -> '{abs_url}'")

    logger.info("Phase 4 Shared Adapter Framework active and operational.")


if __name__ == "__main__":
    main()
