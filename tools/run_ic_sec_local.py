"""
Run IC and SEC checks from THIS computer instead of GitHub.

WHY THIS EXISTS
----------------
insurance.gov.ph and sec.gov.ph block requests coming from GitHub's servers,
so GitHub can only reach them through a paid scraping proxy (ScraperAPI).
Your own home/office internet connection is not blocked, so running IC/SEC
from here needs no proxy at all -- zero ongoing cost.

The tradeoff: this only checks IC/SEC when YOU run it (or when Windows Task
Scheduler runs it for you) -- your PC has to be on and online at that
moment. GitHub can still cover IC/SEC on days this doesn't run, using the
proxy, IF their "Active" checkbox is turned back on in your Sources sheet.

THE SAFETY RULE -- READ THIS
------------------------------
Never have BOTH GitHub and this script checking IC/SEC on the same day. If
both run, they keep separate memories of "have I seen this already," and you
could get duplicate emails, or one side could think something old is new
again. The rule:

  1. Before running this script, set IC and SEC to Inactive in your Sources
     sheet, so GitHub skips them.
  2. When you're done for the day (e.g. before shutting down), set them
     back to Active, so GitHub resumes covering them.

This script checks your Sheet automatically and refuses to run if IC or SEC
still show Active there, unless you pass --force.

FIRST-TIME SETUP -- DO THIS BEFORE THE FIRST REAL RUN
--------------------------------------------------------
This script keeps its own "already seen" memory file, separate from
GitHub's, at the path given by --state-file (default shown below). Before
running this for the first time, run the "Export Current State" GitHub
Actions workflow once, download the file it produces, and save it at that
same path. Skipping this makes the first run either think every existing
issuance is brand new, or silently mark today's real backlog as "already
known" without ever emailing you about it (Foundation §13's baseline rule,
applied against a memory file that doesn't know what GitHub already knows).

USAGE
-----
    python tools/run_ic_sec_local.py

Environment variables needed (same ones you've already used for testing):
    SMTP_SENDER_EMAIL, SMTP_SENDER_PASSWORD, ANTHROPIC_API_KEY
    SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON       (optional)
    NOTIFICATION_RECIPIENTS                     (fallback if no Sheet)

Do NOT set SCRAPER_PROXY_API_KEY. If it happens to be set, this script clears
it for the run so a mistake here can't spend proxy credits. Pass
--allow-proxy if you genuinely want to use the proxy from this machine too.

Running this more than once on the same day is safe: a second run will see
that today's check already happened (recorded in --state-file) and skip
IC/SEC entirely, matching the OPENING_CHECK_ONLY restriction those adapters
already have in production. Use --force to re-check anyway.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_STATE_PATH = REPO_ROOT / "state" / "ic_sec_local_seen_issuances.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--state-file",
        default=str(DEFAULT_STATE_PATH),
        help=f"Where this script keeps its 'already seen' memory (default: {DEFAULT_STATE_PATH}).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even if IC/SEC still show Active in the Sources sheet, or if this "
        "script already ran today. Skips both safety checks -- use deliberately.",
    )
    parser.add_argument(
        "--allow-proxy",
        action="store_true",
        help="Permit ScraperAPI use from this machine too. Off by default, since "
        "the whole point of running here is to avoid needing it.",
    )
    return parser.parse_args()


def _preflight(args: argparse.Namespace, config_reader) -> None:
    print("== Preflight ==")

    if not args.allow_proxy and os.getenv("SCRAPER_PROXY_API_KEY"):
        os.environ.pop("SCRAPER_PROXY_API_KEY")
        print("  proxy                   cleared for this run (direct fetch, 0 credits)")
    else:
        proxy_set = bool(os.getenv("SCRAPER_PROXY_API_KEY"))
        print(f"  proxy                   {'ENABLED -- will spend credits' if proxy_set else 'disabled (direct fetch)'}")

    if not os.getenv("SMTP_SENDER_EMAIL"):
        print("\nERROR: SMTP_SENDER_EMAIL is not set, so nothing would be emailed.")
        print("Set SMTP_SENDER_EMAIL and SMTP_SENDER_PASSWORD before running this for real.")
        sys.exit(1)
    print(f"  email from              {os.getenv('SMTP_SENDER_EMAIL')}")
    print(f"  ANTHROPIC_API_KEY       {'set' if os.getenv('ANTHROPIC_API_KEY') else 'MISSING -- AI summaries will read UNAVAILABLE'}")
    print(f"  state file              {args.state_file}")

    # Duplicate-run safety check: warn/refuse if GitHub might ALSO check
    # IC/SEC today (see the module docstring's safety rule).
    active_sources = config_reader.get_active_sources()
    if active_sources is None:
        print("  Sheet Active check      could not check (Sheet not configured/unreachable) -- proceeding without it")
        print()
        return

    conflicts = sorted(key for key in active_sources if key[0] in ("IC", "SEC"))
    if conflicts and not args.force:
        print("\nERROR: IC/SEC are still marked Active in your Sources sheet:")
        for reg, cat in conflicts:
            print(f"    {reg} / {cat}")
        print("\nIf GitHub also checks today, you risk duplicate emails. Set these to")
        print("Inactive in the Sheet first, or re-run with --force if you're sure")
        print("GitHub won't also check IC/SEC today.")
        sys.exit(1)
    elif conflicts:
        print(f"  Sheet Active check      OVERRIDDEN by --force ({len(conflicts)} categor{'y' if len(conflicts) == 1 else 'ies'} still Active)")
    else:
        print("  Sheet Active check      OK -- IC/SEC are Inactive, GitHub will skip them")
    print()


def main() -> int:
    args = _parse_args()

    import main as pipeline  # the real pipeline, imported late so sys.path is set up first
    from core.sheets_config import SheetsConfigReader
    from core.state import StateManager

    config_reader = SheetsConfigReader()
    _preflight(args, config_reader)

    ic_sec_adapters = [a for a in pipeline.ADAPTERS if a.regulator_id.upper() in ("IC", "SEC")]

    state_path = Path(args.state_file)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_manager = StateManager(filepath=str(state_path))

    # Own-day dedupe, deliberately simpler than core.schedule's
    # resolve_run_decision: that module's OpeningTime/BusinessDays gating
    # exists to solve GitHub's "wakes up every 15 minutes regardless of
    # config" problem, which doesn't apply here -- you decide when to run
    # this. All that's needed locally is "don't treat a second same-day run
    # as a second opening check," which would otherwise send a second empty
    # Daily Monitoring Report when nothing new has appeared since the first.
    schedule_config = config_reader.get_schedule_config()
    try:
        tz = ZoneInfo(schedule_config.get("Timezone", "Asia/Manila"))
    except Exception:
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    today_str = now.date().isoformat()

    if state_manager.get_last_opening_check_date() == today_str and not args.force:
        print(f"Already checked IC/SEC today ({today_str}) from this machine. Nothing to do.")
        print("Use --force to check again anyway.")
        return 0

    print(f"== Running IC/SEC check ({len(ic_sec_adapters)} categories) ==\n")
    try:
        try:
            results = pipeline.run(
                is_opening_check=True,
                state_manager=state_manager,
                config_reader=config_reader,
                adapters=ic_sec_adapters,
            )
        except RuntimeError as err:
            # run() re-raises after finishing everything it could (§3.8) --
            # any category that DID succeed was already notified before this
            # was raised, so report and continue rather than treating this as
            # a total failure.
            print(f"\nOne or more categories failed: {err}")
            print("Any category that succeeded was still notified before this was raised.")
            return 1
        finally:
            # Recorded even on failure, same rationale as main.py's own
            # finally-block: a run that genuinely happened (however
            # degraded) must still be remembered as today's check, or every
            # later invocation today re-treats itself as the first.
            state_manager.record_run(now.isoformat(), True)
    finally:
        print("\nReminder: set IC and SEC back to Active in your Sources sheet")
        print("once you're done, so GitHub can cover them again when this isn't running.")

    print("\n== Result ==")
    print(f"  new issuances detected  {results['total_new']}")
    print(f"  successfully notified   {results['notified']}")
    if results["notified"]:
        print("\n  Check your inbox for the digest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
