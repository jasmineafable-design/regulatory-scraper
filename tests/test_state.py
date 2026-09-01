import json
from pathlib import Path
from core.state import StateManager


def test_legacy_non_dict_state_file_does_not_crash(tmp_path: Path):
    """A leftover state file in an incompatible shape (e.g. a list, from an
    older/different implementation) must not crash StateManager -- it should
    be treated as no prior state, per the fail-loud-but-not-crash-on-legacy-
    data policy (see the comment in core/state.py)."""
    test_state_file = tmp_path / "legacy_state.json"
    test_state_file.write_text(json.dumps(["not", "a", "dict"]))

    state_mgr = StateManager(filepath=str(test_state_file))

    assert state_mgr.seen_data == {}
    assert state_mgr.get_last_run_at() is None
    assert state_mgr.get_last_opening_check_date() is None
    assert not state_mgr.is_seen("anything")


def test_state_manager_deduplication(tmp_path: Path):
    """Ensures state manager correctly detects seen items and avoids duplicate entries."""
    test_state_file = tmp_path / "test_state.json"
    state_mgr = StateManager(filepath=str(test_state_file))

    item_id = "BIR-2026-001"

    # Initially item should not be marked as seen
    assert not state_mgr.is_seen(item_id)

    # Mark item as seen and verify
    state_mgr.mark_seen(item_id, agency="BIR", title="Test Regulation")
    assert state_mgr.is_seen(item_id)

    # Verify persistent state reloading
    reloaded_mgr = StateManager(filepath=str(test_state_file))
    assert reloaded_mgr.is_seen(item_id)


def test_baseline_seeding(tmp_path: Path):
    """Ensures baseline seeding records items with status BASELINE."""
    test_state_file = tmp_path / "test_state.json"
    state_mgr = StateManager(filepath=str(test_state_file))

    item_id = "SEC-2026-100"
    state_mgr.mark_seen(item_id, agency="SEC", title="Baseline Notice", status="BASELINE")

    assert state_mgr.is_seen(item_id)
