import pytest
import os
from src.storage.state_store import StateStore

def test_state_store_commit_and_check(tmp_path):
    test_file = tmp_path / "test_state.json"
    store = StateStore(state_file_path=str(test_file))

    assert not store.is_processed("BIR-2026-001")
    store.commit("BIR-2026-001")
    assert store.is_processed("BIR-2026-001")

    # Reload store from file to test persistence
    new_store_instance = StateStore(state_file_path=str(test_file))
    assert new_store_instance.is_processed("BIR-2026-001")
