import pytest
from unittest.mock import MagicMock
from src.pipeline.orchestrator import RegulatoryPipeline
from src.storage.state_store import StateStore

def test_full_pipeline_end_to_end(tmp_path):
    test_state_file = tmp_path / "integration_state.json"
    state_store = StateStore(state_file_path=str(test_state_file))

    # Mock adapters for BIR, IC, SEC
    bir_adapter = MagicMock()
    bir_adapter.fetch.return_value = [{"title": "BIR RMC 01-2026", "url": "https://bir.gov.ph/rmc01", "regulator": "BIR"}]

    ic_adapter = MagicMock()
    ic_adapter.fetch.return_value = [{"title": "IC CL 2026-05", "url": "https://ic.gov.ph/cl2026-05", "regulator": "IC"}]

    sec_adapter = MagicMock()
    sec_adapter.fetch.return_value = []

    notifier = MagicMock()

    pipeline = RegulatoryPipeline(
        adapters=[bir_adapter, ic_adapter, sec_adapter],
        state_store=state_store,
        notifier=notifier
    )

    # Initial Run (Should detect 2 new issuances)
    result = pipeline.run(is_morning_check=False)
    assert result["total_fetched"] == 2
    assert result["new_processed"] == 2
    assert notifier.send_immediate_briefing.call_count == 1

    # Consecutive Run (Should detect 0 due to state store deduplication)
    result_repeat = pipeline.run(is_morning_check=False)
    assert result_repeat["total_fetched"] == 2
    assert result_repeat["new_processed"] == 0
