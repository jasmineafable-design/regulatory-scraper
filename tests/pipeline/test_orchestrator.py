import pytest
from unittest.mock import MagicMock
from src.pipeline.orchestrator import RegulatoryPipeline
from src.storage.state_store import StateStore

def test_pipeline_immediate_notification_branch(tmp_path):
    # Setup state store and mock adapter
    test_file = tmp_path / "state.json"
    state_store = StateStore(state_file_path=str(test_file))

    mock_adapter = MagicMock()
    mock_adapter.fetch.return_value = [
        {"title": "BIR RMC 10-2026", "url": "https://bir.gov.ph/rmc10-2026", "regulator": "BIR"}
    ]

    mock_notifier = MagicMock()

    pipeline = RegulatoryPipeline(adapters=[mock_adapter], state_store=state_store, notifier=mock_notifier)
    summary = pipeline.run(is_morning_check=False)

    assert summary["new_processed"] == 1
    mock_notifier.send_immediate_briefing.assert_called_once()
    assert state_store.is_processed("https://bir.gov.ph/rmc10-2026")

def test_pipeline_silent_branch(tmp_path):
    test_file = tmp_path / "state.json"
    state_store = StateStore(state_file_path=str(test_file))

    mock_adapter = MagicMock()
    mock_adapter.fetch.return_value = []
    mock_notifier = MagicMock()

    pipeline = RegulatoryPipeline(adapters=[mock_adapter], state_store=state_store, notifier=mock_notifier)
    summary = pipeline.run(is_morning_check=False)

    assert summary["new_processed"] == 0
    mock_notifier.send_immediate_briefing.assert_not_called()
    mock_notifier.send_daily_monitoring_report.assert_not_called()
