"""
Regulatory Scraper — entry point.

Wires the Federated Source Adapters (BIR, IC, SEC) into the Shared Core's
deterministic pipeline: Fetch -> Validate -> Detect -> Assess -> Compose -> Notify
-> Commit State (Foundation §3.6). Assess remains stubbed as "UNAVAILABLE" per the
approved Phase-1 behavior (core/compose.py) — AI integration is Phase 4 and is not
part of this consolidation.

One adapter's failure is isolated from the others (§3.4 principle 3) but is never
swallowed (§3.4 principle 2): failures are collected and re-raised after every
adapter has had a chance to run, so the scheduling platform's own native
failure notification fires (§3.8).

Which (regulator, category) pairs actually run, who's notified for each, and
whether "now" should run a check at all (and if so, whether it's the business
day's opening check) are all Sheet-configurable per §3.2 — see
core/sheets_config.py and core/schedule.py.
"""

import argparse
import logging
from datetime import datetime
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

from models.issuance import BriefingRecord, CandidateIssuance
from core.commit_state import StateCommitter
from core.compose import Composer
from core.detect import Detector
from core.logger import setup_logger
from core.notify import ConsoleNotificationChannel, NotificationDispatcher
from core.notify_channels import EmailNotificationChannel
from core.schedule import resolve_run_decision
from core.sheets_config import SheetsConfigReader
from core.state import StateManager
from core.adapters import BIRAdapter, ICAdapter, SECAdapter

logger = setup_logger("main")

ADAPTERS = [BIRAdapter(), ICAdapter(), SECAdapter()]


def build_notification_channel(recipient_matrix: Dict[Tuple[str, str], List[str]]):
    import os

    if os.getenv("SMTP_SENDER_EMAIL"):
        return EmailNotificationChannel(recipient_matrix=recipient_matrix)
    logger.warning(
        "SMTP_SENDER_EMAIL not configured; falling back to console notification "
        "channel (nothing will actually be emailed)."
    )
    return ConsoleNotificationChannel()


def _select_active_adapters(config_reader: SheetsConfigReader) -> List:
    """Filters ADAPTERS down to (regulator, category) pairs marked Active in the
    Sources sheet (§3.2). Fail-open when the Sheet is unconfigured/unreachable —
    get_active_sources() returns None in that case, meaning "no filter, run
    everything" rather than silently disabling all monitoring (§3.8)."""
    active_sources = config_reader.get_active_sources()
    if active_sources is None:
        return list(ADAPTERS)

    selected = []
    for adapter in ADAPTERS:
        key = (adapter.regulator_id.upper(), getattr(adapter, "category", "").upper())
        if key in active_sources:
            selected.append(adapter)
        else:
            logger.info(f"[{key[0]}/{key[1]}] Skipped this run — not marked Active in the Sources sheet.")
    return selected


def _baseline_new_categories(
    detector: Detector, state_manager: StateManager, candidates: List[CandidateIssuance]
) -> List[CandidateIssuance]:
    """Applies the §13 baseline-exclusion rule per (regulator, category) pair
    present in this fetch. A category being seen for the first time ever has its
    backlog recorded as known, without notifying — everything else proceeds
    normally."""
    remaining = list(candidates)
    categories = {(c.source_regulator, c.source_category) for c in candidates}

    for regulator, category in categories:
        if state_manager.is_category_baselined(regulator, category):
            continue
        batch = [c for c in remaining if c.source_regulator == regulator and c.source_category == category]
        detector.detect_new_issuances(batch, is_category_baseline=True)
        logger.info(f"Baselined {len(batch)} item(s) for {regulator}/{category} (first-ever run).")
        remaining = [c for c in remaining if not (c.source_regulator == regulator and c.source_category == category)]

    return remaining


def run(is_opening_check: bool, state_manager: "StateManager" = None, config_reader: "SheetsConfigReader" = None) -> dict:
    config_reader = config_reader or SheetsConfigReader()
    recipient_matrix = config_reader.get_recipient_matrix()

    state_manager = state_manager or StateManager()
    detector = Detector(state_manager)
    composer = Composer()
    committer = StateCommitter(state_manager)
    channel = build_notification_channel(recipient_matrix)
    dispatcher = NotificationDispatcher(channel)

    all_briefings: List[BriefingRecord] = []
    adapter_errors: List[str] = []

    active_adapters = _select_active_adapters(config_reader)

    for adapter in active_adapters:
        try:
            candidates = adapter.fetch_latest_issuances()
        except Exception as e:
            # Isolate this adapter's failure (§3.4 principle 3) — other adapters
            # still run — but never swallow it (§3.4 principle 2).
            logger.error(f"[{adapter.regulator_id}] Fetch/Validate failed: {e}", exc_info=True)
            adapter_errors.append(f"{adapter.regulator_id}: {e}")
            continue

        candidates = _baseline_new_categories(detector, state_manager, candidates)
        new_candidates = detector.detect_new_issuances(candidates, is_category_baseline=False)

        for candidate in new_candidates:
            all_briefings.append(composer.compose_briefing(candidate))

    notified = dispatcher.dispatch(all_briefings, is_opening_check=is_opening_check, check_timestamp_info="opening check" if is_opening_check else "recurring check")
    committer.commit_notified_briefings(notified)

    result = {
        "total_new": len(all_briefings),
        "notified": len(notified),
        "adapter_errors": adapter_errors,
        "is_opening_check": is_opening_check,
    }

    if adapter_errors:
        # Fail loud (§3.8): raise after finishing everything that could be
        # finished, so the scheduling platform's own failure notification fires.
        raise RuntimeError(f"One or more adapters failed this run: {adapter_errors}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Regulatory Scraper pipeline run.")
    parser.add_argument(
        "--opening-run",
        action="store_true",
        dest="opening_run",
        help="Force this run to be treated as the business day's opening check "
        "(§3.7), regardless of what core.schedule would otherwise decide. Intended "
        "for manual/workflow_dispatch overrides, not routine scheduled invocations.",
    )
    args = parser.parse_args()

    config_reader = SheetsConfigReader()
    state_manager = StateManager()
    schedule_config = config_reader.get_schedule_config()

    try:
        tz = ZoneInfo(schedule_config.get("Timezone", "Asia/Manila"))
    except Exception:
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)

    decision = resolve_run_decision(
        schedule_config=schedule_config,
        last_run_at=state_manager.get_last_run_at(),
        last_opening_check_date=state_manager.get_last_opening_check_date(),
        force_opening_run=args.opening_run,
        now=now,
    )

    if not decision.should_run:
        # Not a failure -- this is an expected no-op wake-up under the ceiling
        # cron (outside business hours/days, before opening time, or too soon
        # after the last check per the Sheet-configured interval). Exit 0 so
        # the scheduling platform's fail-loud mechanism (§3.8) stays reserved
        # for genuine errors, not routine schedule gating.
        logger.info(f"Skipping this invocation: {decision.reason}")
        return

    logger.info(f"Starting pipeline run (opening_check={decision.is_opening_check}): {decision.reason}")
    results = run(is_opening_check=decision.is_opening_check, state_manager=state_manager, config_reader=config_reader)
    # Recorded in the same timezone used to make the decision above, so a run
    # near local midnight is never misfiled under the wrong calendar day.
    state_manager.record_run(now.isoformat(), decision.is_opening_check)
    logger.info(f"Pipeline run complete: {results}")


if __name__ == "__main__":
    main()
