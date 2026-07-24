import json
from pathlib import Path
from core.models import ContentQuality, NormalizedIssuance
from core.state import StateManager


def test_state_manager_deduplication(tmp_path: Path):
    """Ensures state manager correctly detects seen items and avoids duplicate entries."""
    test_state_file = tmp_path / "test_state.json"
    state_mgr = StateManager(file_path=test_state_file)

    sample = NormalizedIssuance(
        issuance_id="TEST_REG_101",
        regulator_id="TEST",
        category_id="CAT1",
        title="Test Regulation Title",
        canonical_url="https://example.com/test101",
        content_quality=ContentQuality.VALID,
    )

    # 1. Initially unseen
    assert not state_mgr.is_seen(sample.issuance_id)

    # 2. Record and commit
    state_mgr.record_issuance(sample)
    state_mgr.commit()

    # 3. Now seen
    assert state_mgr.is_seen(sample.issuance_id)

    # 4. Reload new instance from same file to test persistence
    reloaded_state = StateManager(file_path=test_state_file)
    assert reloaded_state.is_seen(sample.issuance_id)


def test_baseline_seeding(tmp_path: Path):
    """Ensures baseline seeding records items with status BASELINE."""
    test_state_file = tmp_path / "test_state.json"
    state_mgr = StateManager(file_path=test_state_file)

    sample = NormalizedIssuance(
        issuance_id="HISTORIC_CIRCULAR_001",
        regulator_id="BIR",
        category_id="RMC",
        title="Historic Circular",
        canonical_url="https://example.com/historic001",
        content_quality=ContentQuality.VALID,
    )

    state_mgr.seed_baseline(sample)
    state_mgr.commit()

    assert state_mgr.is_seen("HISTORIC_CIRCULAR_001")
    assert state_mgr.records["HISTORIC_CIRCULAR_001"]["processed_status"] == "BASELINE"
