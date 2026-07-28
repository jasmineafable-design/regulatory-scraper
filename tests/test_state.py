from pathlib import Path
from core.state import StateManager


def test_state_manager_deduplication(tmp_path: Path):
    """Ensures state manager correctly detects seen items and avoids duplicate entries."""
    test_state_file = tmp_path / "test_state.json"
    state_mgr = StateManager(state_file=str(test_state_file))

    item_id = "BIR-2026-001"

    # Initially item should not be marked as seen
    assert not state_mgr.is_seen(item_id)

    # Mark item as seen and verify
    state_mgr.mark_seen(item_id, agency="BIR", title="Test Regulation")
    assert state_mgr.is_seen(item_id)

    # Verify persistent state reloading
    reloaded_mgr = StateManager(state_file=str(test_state_file))
    assert reloaded_mgr.is_seen(item_id)


def test_baseline_seeding(tmp_path: Path):
    """Ensures baseline seeding records items with status BASELINE."""
    test_state_file = tmp_path / "test_state.json"
    state_mgr = StateManager(state_file=str(test_state_file))

    item_id = "SEC-2026-100"
    state_mgr.mark_seen(item_id, agency="SEC", title="Baseline Notice", status="BASELINE")

    assert state_mgr.is_seen(item_id)
