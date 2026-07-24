from core.config import SystemConfig
from core.logger import setup_logger

logger = setup_logger("main")


def main() -> None:
    """Primary system entry point."""
    logger.info("Initializing Regulatory Scraper System...")

    # Load system configuration
    config = SystemConfig.load()

    logger.info(f"System Environment: {config.environment}")
    logger.info("Active Regulatory Targets Configured:")
    
    for target in config.targets:
        status = "ENABLED" if target.enabled else "DISABLED"
        logger.info(
            f"  - [{status}] {target.regulator_id} ({target.category_id}): {target.category_name} (Interval: {target.check_interval_hours}h)"
        )

    logger.info("Configured Business Context Entities:")
    for entity in config.entities:
        logger.info(
            f"  - [{entity.entity_code}] {entity.entity_full_name} Focus: {entity.primary_focus}"
        )

    logger.info("Phase 2 Configuration Subsystem active and operational.")


if __name__ == "__main__":
    main()
