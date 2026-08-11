"""
Schedule decision logic (Foundation §3.2/§3.3).

The Foundation requires the business-day calendar, opening-check time, and
recurring polling interval to be non-technical-user-editable (§3.2). GitHub
Actions' own `schedule:` trigger is evaluated entirely by GitHub's
infrastructure before any of this repository's code runs, so the cron
expression in the workflow YAML can never itself be replaced by Sheet
configuration — that is an inherent platform limitation (see the workflow's
own comments), not a gap in this module.

What this module does instead: the workflow wakes up on a frequent, fixed
*ceiling* cadence (wide enough to cover any sensible Sheet configuration), and
this module decides — using the Sheet's configured BusinessDays/OpeningTime/
PollingIntervalMinutes/Timezone — whether a given wake-up should actually
execute a check, and if so, whether it's the business day's opening check
(§3.7). This makes the effective schedule genuinely Sheet-editable, within
the fixed technical ceiling of how often the platform can wake the job up.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


@dataclass
class RunDecision:
    should_run: bool
    is_opening_check: bool
    reason: str


def resolve_run_decision(
    schedule_config: Dict[str, str],
    last_run_at: Optional[str],
    last_opening_check_date: Optional[str],
    force_opening_run: bool = False,
    now: Optional[datetime] = None,
) -> RunDecision:
    """Decides whether this invocation should run a check, and whether it's
    the opening check, per the Sheet-configured schedule parameters.

    Deliberately fails toward *not* skipping business behavior: any parsing
    error in the Sheet's schedule values falls back to the documented defaults
    rather than raising, consistent with SheetsConfigReader's own fail-open
    convention for configuration (never for state or delivery — §3.8).
    """
    try:
        tz = ZoneInfo(schedule_config.get("Timezone", "Asia/Manila"))
    except Exception:
        tz = ZoneInfo("UTC")
    now = (now or datetime.now(tz)).astimezone(tz)
    today_str = now.date().isoformat()

    business_days = {
        d.strip()[:3].lower()
        for d in schedule_config.get("BusinessDays", "Mon,Tue,Wed,Thu,Fri").split(",")
        if d.strip()
    }
    is_business_day = now.strftime("%a").lower() in business_days

    if force_opening_run:
        return RunDecision(True, True, "force_opening_run explicitly requested.")

    if not is_business_day:
        return RunDecision(False, False, f"{now.strftime('%A')} is not a configured business day.")

    try:
        opening_hour, opening_minute = (
            int(p) for p in schedule_config.get("OpeningTime", "10:00").split(":")
        )
    except (ValueError, TypeError):
        logger.warning(
            f"Could not parse OpeningTime {schedule_config.get('OpeningTime')!r}; defaulting to 10:00."
        )
        opening_hour, opening_minute = 10, 0
    opening_dt = now.replace(hour=opening_hour, minute=opening_minute, second=0, microsecond=0)

    try:
        interval_minutes = int(schedule_config.get("PollingIntervalMinutes", "30"))
    except (ValueError, TypeError):
        logger.warning(
            f"Could not parse PollingIntervalMinutes "
            f"{schedule_config.get('PollingIntervalMinutes')!r}; defaulting to 30."
        )
        interval_minutes = 30

    already_opened_today = last_opening_check_date == today_str

    if not already_opened_today:
        if now >= opening_dt:
            return RunDecision(True, True, "First run at/after the configured opening time today.")
        return RunDecision(
            False, False, f"Before the configured opening time ({opening_dt.strftime('%H:%M %Z')})."
        )

    # Opening check already happened today -- this can only be a recurring check.
    elapsed = timedelta(minutes=interval_minutes)  # safe default if we can't compute a real elapsed time
    if last_run_at:
        try:
            last_run_dt = datetime.fromisoformat(last_run_at)
            if last_run_dt.tzinfo is None:
                last_run_dt = last_run_dt.replace(tzinfo=tz)
            elapsed = now - last_run_dt.astimezone(tz)
        except ValueError:
            logger.warning(f"Could not parse last_run_at {last_run_at!r}; assuming interval has elapsed.")

    if elapsed >= timedelta(minutes=interval_minutes):
        return RunDecision(True, False, "Configured polling interval has elapsed since the last run.")
    return RunDecision(
        False, False, "Configured polling interval has not yet elapsed since the last run."
    )
