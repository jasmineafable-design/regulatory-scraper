import logging
from datetime import datetime, timezone
from core.models import CandidateIssuance
from core.detect import detect_new_issuances
from core.compose import compose_briefing
from core.notify import send_notification
from state.manager import commit_issuance_to_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("PipelineRunner")


def run_deterministic_pipeline(candidates: list[CandidateIssuance]) -> None:
    """
    Executes the deterministic shared core pipeline:
    Detect -> Compose -> Notify -> Commit State
    """
    logger.info(f"Starting pipeline execution with {len(candidates)} candidate(s)...")

    # 1. DETECT (Filter duplicates)
    new_candidates = detect_new_issuances(candidates)
    logger.info(f"Detection complete. Found {len(new_candidates)} new candidate(s).")

    if not new_candidates:
        logger.info("No new issuances to process.")
        return

    # Process each new candidate through Compose, Notify, and Commit
    for candidate in new_candidates:
        logger.info(f"Processing issuance: {candidate.issuance_identifier} ({candidate.source_regulator})")

        # 2. COMPOSE
        briefing = compose_briefing(candidate=candidate)

        # 3. NOTIFY (Must happen BEFORE state commitment)
        notification_success = send_notification(briefing)

        if not notification_success:
            logger.error(
                f"Notification failed for {candidate.issuance_identifier}. "
                "Aborting state commit to allow re-attempt on next run."
            )
            continue

        # Update notified timestamp
        now_iso = datetime.now(timezone.utc).isoformat()
        briefing.notified_at = now_iso

        # 4. COMMIT STATE (Only after successful notification)
        briefing.committed_at = now_iso
        commit_issuance_to_state(
            regulator=briefing.source_regulator,
            identifier=briefing.issuance_identifier,
            record_data=briefing.model_dump()
        )
        logger.info(f"Successfully committed {briefing.issuance_identifier} to state.")


if __name__ == "__main__":
    # Sample candidate to verify end-to-end functionality in Phase 1
    sample_candidate = CandidateIssuance(
        source_regulator="BIR",
        source_category="Revenue Memorandum Circular",
        issuance_identifier="RMC-2026-99",
        issuance_title="Sample Circular for Pipeline Verification",
        source_url="https://www.bir.gov.ph/rmc-2026-99",
        raw_payload={"sample_key": "sample_value"},
        validation_status="genuine"
    )

    run_deterministic_pipeline([sample_candidate])
