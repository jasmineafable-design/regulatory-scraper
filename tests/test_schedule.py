from datetime import datetime
from zoneinfo import ZoneInfo

from core.schedule import resolve_run_decision

TZ = ZoneInfo("Asia/Manila")

DEFAULT_SCHEDULE = {
    "BusinessDays": "Mon,Tue,Wed,Thu,Fri",
    "OpeningTime": "10:00",
    "PollingIntervalMinutes": "30",
    "Timezone": "Asia/Manila",
}


def test_weekend_never_runs():
    saturday_10am = datetime(2026, 8, 8, 10, 0, tzinfo=TZ)  # 2026-08-08 is a Saturday
    decision = resolve_run_decision(DEFAULT_SCHEDULE, None, None, now=saturday_10am)
    assert decision.should_run is False
    assert decision.is_opening_check is False


def test_before_opening_time_does_not_run():
    monday_9am = datetime(2026, 8, 3, 9, 0, tzinfo=TZ)
    decision = resolve_run_decision(DEFAULT_SCHEDULE, None, None, now=monday_9am)
    assert decision.should_run is False


def test_first_run_at_opening_time_is_the_opening_check():
    monday_10am = datetime(2026, 8, 3, 10, 0, tzinfo=TZ)
    decision = resolve_run_decision(DEFAULT_SCHEDULE, None, None, now=monday_10am)
    assert decision.should_run is True
    assert decision.is_opening_check is True


def test_after_opening_check_recurring_run_waits_for_interval():
    monday_1015am = datetime(2026, 8, 3, 10, 15, tzinfo=TZ)
    last_run_at = datetime(2026, 8, 3, 10, 0, tzinfo=TZ).isoformat()
    decision = resolve_run_decision(
        DEFAULT_SCHEDULE, last_run_at, "2026-08-03", now=monday_1015am
    )
    assert decision.should_run is False, "Only 15 of 30 configured minutes have elapsed."


def test_after_opening_check_recurring_run_fires_once_interval_elapses():
    monday_1030am = datetime(2026, 8, 3, 10, 30, tzinfo=TZ)
    last_run_at = datetime(2026, 8, 3, 10, 0, tzinfo=TZ).isoformat()
    decision = resolve_run_decision(
        DEFAULT_SCHEDULE, last_run_at, "2026-08-03", now=monday_1030am
    )
    assert decision.should_run is True
    assert decision.is_opening_check is False


def test_force_opening_run_overrides_everything():
    saturday = datetime(2026, 8, 8, 3, 0, tzinfo=TZ)
    decision = resolve_run_decision(
        DEFAULT_SCHEDULE, None, None, force_opening_run=True, now=saturday
    )
    assert decision.should_run is True
    assert decision.is_opening_check is True


def test_sheet_configured_interval_is_respected():
    """A shorter Sheet-configured interval (15 min) should let a recurring
    check fire sooner than the 30-minute default would."""
    schedule = {**DEFAULT_SCHEDULE, "PollingIntervalMinutes": "15"}
    monday_1015am = datetime(2026, 8, 3, 10, 15, tzinfo=TZ)
    last_run_at = datetime(2026, 8, 3, 10, 0, tzinfo=TZ).isoformat()
    decision = resolve_run_decision(schedule, last_run_at, "2026-08-03", now=monday_1015am)
    assert decision.should_run is True


def test_sheet_configured_opening_time_is_respected():
    schedule = {**DEFAULT_SCHEDULE, "OpeningTime": "08:00"}
    monday_8am = datetime(2026, 8, 3, 8, 0, tzinfo=TZ)
    decision = resolve_run_decision(schedule, None, None, now=monday_8am)
    assert decision.should_run is True
    assert decision.is_opening_check is True


def test_malformed_schedule_values_fall_back_to_defaults_without_raising():
    schedule = {"OpeningTime": "not-a-time", "PollingIntervalMinutes": "lots"}
    monday_10am = datetime(2026, 8, 3, 10, 0, tzinfo=TZ)
    decision = resolve_run_decision(schedule, None, None, now=monday_10am)
    assert decision.should_run is True
    assert decision.is_opening_check is True
