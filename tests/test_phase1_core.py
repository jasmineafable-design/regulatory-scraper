from pathlib import Path
from models.issuance import CandidateIssuance
from core.state import StateManager
from core.detect import Detector
from core.compose import Composer
from core.notify import NotificationDispatcher, ConsoleNotificationChannel
from core.commit_state import StateCommitter


def test_phase1_deterministic_flow(tmp_path: Path):
    """Tests full Phase 1 flow with synthetic candidates."""
    state_file = tmp_path / "test_state.json"
    state_mgr = StateManager(filepath=str(state_file))

    detector = Detector(state_mgr)
    composer = Composer()
    dispatcher = NotificationDispatcher(ConsoleNotificationChannel())
    committer = StateCommitter(state_mgr)

    candidate = CandidateIssuance(
        source_regulator="BIR",
        source_category="BIR-RMC",
        issuance_identifier="RMC-2026-001",
        issuance_title="Test Revenue Memorandum Circular",
        source_url="https://www.bir.gov.ph/test",
        raw_content_reference="Raw body content",
    )

    # 1. Detect
    new_candidates = detector.detect_new_issuances([candidate])
    assert len(new_candidates) == 1

    # 2. Compose
    briefings = [composer.compose_briefing(c) for c in new_candidates]
    assert briefings[0].executive_summary == "UNAVAILABLE"
    assert briefings[0].completeness_status == "degraded"

    # 3. Notify (Opening check with item -> Briefing sent)
    notified = dispatcher.dispatch(briefings, is_opening_check=True)
    assert len(notified) == 1

    # 4. Commit
    committer.commit_notified_briefings(notified)
    assert state_mgr.is_seen("RMC-2026-001")

    # Re-run -> Should be filtered out by Detect
    new_candidates_2 = detector.detect_new_issuances([candidate])
    assert len(new_candidates_2) == 0


def test_opening_check_empty_sends_report(tmp_path: Path):
    """Opening check with 0 items triggers Daily Monitoring Report."""
    state_file = tmp_path / "test_state.json"
    state_mgr = StateManager(filepath=str(state_file))

    dispatcher = NotificationDispatcher(ConsoleNotificationChannel())
    notified = dispatcher.dispatch([], is_opening_check=True)
    assert len(notified) == 0


def test_recurring_check_empty_sends_nothing(tmp_path: Path):
    """Recurring check with 0 items produces no output."""
    state_file = tmp_path / "test_state.json"
    state_mgr = StateManager(filepath=str(state_file))

    dispatcher = NotificationDispatcher(ConsoleNotificationChannel())
    notified = dispatcher.dispatch([], is_opening_check=False)
    assert len(notified) == 0


def test_baseline_category_exclusion(tmp_path: Path):
    """Baselining a category records state without returning new items."""
    state_file = tmp_path / "test_state.json"
    state_mgr = StateManager(filepath=str(state_file))
    detector = Detector(state_mgr)

    candidate = CandidateIssuance(
        source_regulator="IC",
        source_category="IC-CL",
        issuance_identifier="CL-2026-010",
        issuance_title="Baseline Circular",
        source_url="https://www.insurance.gov.ph/test",
        raw_content_reference="Raw body content",
    )

    new_candidates = detector.detect_new_issuances([candidate], is_category_baseline=True)
    assert len(new_candidates) == 0
    assert state_mgr.is_seen("CL-2026-010")
