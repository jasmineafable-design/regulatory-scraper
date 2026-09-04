"""Regression tests for main.run()'s `adapters` parameter, added 2026-09-04
so tools/run_ic_sec_local.py can run a subset (IC/SEC only) of the full
ADAPTERS pool from a machine that isn't proxy-blocked, without touching
production's own invocation (which never passes this and is unaffected)."""

from unittest.mock import MagicMock, patch

from models.issuance import CandidateIssuance

import main as pipeline


def _fake_adapter(regulator, category, n=1):
    adapter = MagicMock()
    adapter.regulator_id = regulator
    adapter.category = category
    adapter.OPENING_CHECK_ONLY = False
    adapter.fetch_latest_issuances.return_value = [
        CandidateIssuance(
            source_regulator=regulator,
            source_category=category,
            issuance_identifier=f"{category} No. {i}",
            issuance_title=f"{category} test {i}",
            source_url="https://x.test",
            raw_content_reference="<a/>",
            validation_status="genuine",
        )
        for i in range(1, n + 1)
    ]
    return adapter


def _config_reader():
    reader = MagicMock()
    reader.get_active_sources.return_value = None
    reader.get_recipient_matrix.return_value = {}
    return reader


def test_run_with_adapters_param_only_fetches_that_pool(tmp_path):
    bir = _fake_adapter("BIR", "RMC")
    ic = _fake_adapter("IC", "IC-CL")

    with patch.object(pipeline, "ADAPTERS", [bir, ic]), \
         patch.object(pipeline, "build_notification_channel", lambda m: pipeline.ConsoleNotificationChannel()):
        pipeline.run(
            is_opening_check=True,
            state_manager=pipeline.StateManager(filepath=str(tmp_path / "state.json")),
            config_reader=_config_reader(),
            adapters=[ic],  # restrict to IC only, even though ADAPTERS has both
        )

    bir.fetch_latest_issuances.assert_not_called()
    ic.fetch_latest_issuances.assert_called_once()


def test_run_without_adapters_param_uses_full_module_pool_unchanged(tmp_path):
    """Production's own call site (main()) never passes `adapters` -- confirms
    that path is unaffected by this parameter's addition."""
    bir = _fake_adapter("BIR", "RMC")
    ic = _fake_adapter("IC", "IC-CL")

    with patch.object(pipeline, "ADAPTERS", [bir, ic]), \
         patch.object(pipeline, "build_notification_channel", lambda m: pipeline.ConsoleNotificationChannel()):
        pipeline.run(
            is_opening_check=True,
            state_manager=pipeline.StateManager(filepath=str(tmp_path / "state.json")),
            config_reader=_config_reader(),
        )

    bir.fetch_latest_issuances.assert_called_once()
    ic.fetch_latest_issuances.assert_called_once()


def test_adapters_param_still_respects_sheet_active_filter(tmp_path):
    """The subset passed via `adapters` is still filtered by the Sources
    sheet's Active column, same as the full pool always has been."""
    ic_cl = _fake_adapter("IC", "IC-CL")
    ic_mc = _fake_adapter("IC", "IC-MC")

    reader = MagicMock()
    reader.get_active_sources.return_value = {("IC", "IC-CL")}  # IC-MC not Active
    reader.get_recipient_matrix.return_value = {}

    with patch.object(pipeline, "build_notification_channel", lambda m: pipeline.ConsoleNotificationChannel()):
        pipeline.run(
            is_opening_check=True,
            state_manager=pipeline.StateManager(filepath=str(tmp_path / "state.json")),
            config_reader=reader,
            adapters=[ic_cl, ic_mc],
        )

    ic_cl.fetch_latest_issuances.assert_called_once()
    ic_mc.fetch_latest_issuances.assert_not_called()
