"""
End-to-end test: prove you actually receive a regulatory briefing digest
covering BIR, IC and SEC issuances.

WHY THIS SCRIPT EXISTS
----------------------
Just running `python main.py --opening-run` does NOT prove the digest works,
because of two behaviours that both correctly suppress it:

  1. Baseline exclusion (Foundation §13). The first-ever successful fetch of a
     (regulator, category) pair records its whole backlog as known WITHOUT
     notifying, so you don't get 50 emails about old circulars.
  2. Deduplication. Already-baselined categories only notify on genuinely new
     issuances -- and on most days there aren't any.

In both cases you receive the "Daily Monitoring Report -- no new issuances"
email. That proves SMTP works, but never exercises the digest: the AI
assessment, the table formatting, or the per-category recipient routing.

WHAT IT DOES
------------
Two passes against a THROWAWAY state file, so your real
state/seen_issuances.json is never touched:

  Pass 1  Fetch every selected category and record everything as baseline.
          No email. This makes every category "known".
  Pass 2  Forget the N most recent issuances per category, then run the real
          main.run() pipeline. Those items re-detect as new, so you get a
          genuine digest email -- same code path, same formatting, same
          recipients as production.

USAGE
-----
Set these first (PowerShell):

    $env:SMTP_SENDER_EMAIL="jasmine.afable@moneeinsure.com.ph"
    $env:SMTP_SENDER_PASSWORD="<gmail app password>"
    $env:ANTHROPIC_API_KEY="<key>"
    $env:SHEET_ID="<sheet id>"
    $env:GOOGLE_SERVICE_ACCOUNT_JSON="<json, or path>"

Then, from the repo root:

    python tools/test_digest_email.py --dry-run     # print, don't email
    python tools/test_digest_email.py               # actually email you
    python tools/test_digest_email.py --replay 1 --regulators IC,SEC

IMPORTANT: run this locally, NOT in GitHub Actions. Locally your own IP is
not datacenter-blocked, so IC and SEC are fetched directly and this costs
ZERO ScraperAPI credits. The script refuses to use the proxy unless you pass
--allow-proxy.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

TEST_STATE_PATH = REPO_ROOT / "state" / "_digest_test_state.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--replay",
        type=int,
        default=2,
        help="How many of the most recent issuances per category to re-detect as new (default: 2).",
    )
    parser.add_argument(
        "--regulators",
        default="BIR,IC,SEC",
        help="Comma-separated regulators to include (default: BIR,IC,SEC).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the digest to the console instead of emailing it.",
    )
    parser.add_argument(
        "--allow-proxy",
        action="store_true",
        help="Permit ScraperAPI use. Off by default so a local test can't spend credits.",
    )
    parser.add_argument(
        "--keep-state",
        action="store_true",
        help="Don't delete the throwaway state file at the end (useful for inspecting it).",
    )
    return parser.parse_args()


def _preflight(args: argparse.Namespace) -> None:
    """Fail early and clearly on the misconfigurations that otherwise produce a
    confusingly successful-looking run."""
    print("== Preflight ==")

    if not args.allow_proxy and os.getenv("SCRAPER_PROXY_API_KEY"):
        # Left set, IC/SEC would route through the metered proxy even though a
        # direct fetch from this machine works fine.
        os.environ.pop("SCRAPER_PROXY_API_KEY")
        print("  SCRAPER_PROXY_API_KEY  unset for this run (direct fetch, 0 credits)")
    else:
        print(f"  proxy                  {'ENABLED -- will spend credits' if os.getenv('SCRAPER_PROXY_API_KEY') else 'disabled (direct fetch)'}")

    if args.dry_run:
        # build_notification_channel picks the email channel purely on the
        # presence of this var, so clearing it forces the console channel.
        os.environ.pop("SMTP_SENDER_EMAIL", None)
        print("  mode                   DRY RUN (console output, no email sent)")
    else:
        sender = os.getenv("SMTP_SENDER_EMAIL")
        if not sender:
            print("\nERROR: SMTP_SENDER_EMAIL is not set, so nothing would be emailed --")
            print("the pipeline would silently fall back to console output and the test")
            print("would 'pass' without proving anything. Set it, or pass --dry-run.")
            sys.exit(1)
        print(f"  email from             {sender}")

    print(f"  ANTHROPIC_API_KEY      {'set' if os.getenv('ANTHROPIC_API_KEY') else 'MISSING -- AI summary fields will read UNAVAILABLE'}")
    print(f"  SHEET_ID               {'set' if os.getenv('SHEET_ID') else 'not set -- will fail open (all sources active)'}")
    print(f"  throwaway state        {TEST_STATE_PATH}")
    print()


def main() -> int:
    args = _parse_args()
    _preflight(args)

    # Point state at the throwaway file BEFORE core.config is imported, since
    # Settings reads the env var once at import time.
    os.environ["STATE_FILE_PATH"] = str(TEST_STATE_PATH)
    TEST_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TEST_STATE_PATH.exists():
        # Must start from empty, or leftovers from a previous run would make
        # items look already-seen and pass 2 would find nothing new.
        try:
            TEST_STATE_PATH.unlink()
        except OSError:
            TEST_STATE_PATH.write_text("{}", encoding="utf-8")

    import main as pipeline
    from core.state import StateManager
    from core.sheets_config import SheetsConfigReader

    wanted = {r.strip().upper() for r in args.regulators.split(",") if r.strip()}
    adapters = [a for a in pipeline.ADAPTERS if a.regulator_id.upper() in wanted]
    if not adapters:
        print(f"ERROR: no adapters match --regulators {args.regulators}")
        return 1

    state = StateManager(filepath=str(TEST_STATE_PATH))

    # ---- Pass 1: baseline everything -------------------------------------
    print("== Pass 1: fetching and baselining (no email) ==")
    fetch_order = defaultdict(list)
    failures = []

    for adapter in adapters:
        label = f"{adapter.regulator_id}/{getattr(adapter, 'category', '?')}"
        try:
            candidates = adapter.fetch_latest_issuances()
        except Exception as err:
            failures.append((label, err))
            print(f"  {label:<18} FAILED: {type(err).__name__}: {err}")
            continue

        print(f"  {label:<18} {len(candidates)} issuance(s)")
        for candidate in candidates:
            # Order matters: these sites list newest first, so the first N are
            # the ones worth replaying in pass 2.
            fetch_order[label].append(candidate.issuance_identifier)
            state.mark_seen(
                item_id=candidate.issuance_identifier,
                agency=candidate.source_regulator,
                title=candidate.issuance_title,
                status="BASELINE",
                category=candidate.source_category,
            )

    if failures:
        print(f"\n  {len(failures)} category/categories could not be fetched (see above).")
    if not fetch_order:
        print("\nERROR: nothing was fetched at all, so there's nothing to test.")
        print("Check the errors above -- this is a fetch problem, not an email problem.")
        return 1

    # ---- Forget the most recent N per category ---------------------------
    print(f"\n== Forgetting the {args.replay} most recent issuance(s) per category ==")
    data = json.loads(TEST_STATE_PATH.read_text(encoding="utf-8"))
    forgotten = []
    for label, identifiers in fetch_order.items():
        for identifier in identifiers[: args.replay]:
            if data.pop(identifier, None) is not None:
                forgotten.append((label, identifier))
                print(f"  {label:<18} {identifier}")
    TEST_STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    if not forgotten:
        print("\nERROR: nothing was forgotten, so pass 2 would find no new issuances.")
        return 1

    # ---- Pass 2: real pipeline, real notification ------------------------
    print(f"\n== Pass 2: running the real pipeline over {len(forgotten)} 'new' issuance(s) ==")
    print("   (fetches again -- this is the production code path, including AI assessment)\n")

    try:
        results = pipeline.run(
            is_opening_check=True,  # required, or IC and SEC skip themselves
            state_manager=StateManager(filepath=str(TEST_STATE_PATH)),
            config_reader=SheetsConfigReader(),
        )
    except RuntimeError as err:
        # run() deliberately re-raises after finishing everything it could, so
        # the scheduler's fail-loud path fires (§3.8). For this test that's not
        # fatal: the digest for the categories that DID work has already been
        # sent by the time it raises. Report and carry on.
        print(f"\n  Pipeline raised (expected when any adapter fails): {err}\n")
        print("  Some categories failed, but any digest for the ones that succeeded")
        print("  was already sent before the raise. Check your inbox.")
        return 0

    print("\n== Result ==")
    print(f"  new issuances detected  {results['total_new']}")
    print(f"  successfully notified   {results['notified']}")
    if results["adapter_errors"]:
        print(f"  adapter errors          {len(results['adapter_errors'])}")

    if results["notified"] and not args.dry_run:
        print(f"\n  Check {os.getenv('SMTP_SENDER_EMAIL', 'your inbox')} for a digest")
        print(f"  covering {results['notified']} issuance(s).")
    elif results["notified"]:
        print("\n  Digest printed above (dry run).")
    else:
        print("\n  WARNING: 0 issuances were notified, so no digest was sent.")
        print("  If detection found items but notification didn't, the recipient matrix")
        print("  in your Sources sheet likely has no recipients for these categories.")

    return 0


if __name__ == "__main__":
    exit_code = 1
    try:
        exit_code = main()
    finally:
        if "--keep-state" not in sys.argv and TEST_STATE_PATH.exists():
            try:
                TEST_STATE_PATH.unlink()
                print("\n(throwaway state file removed; real state was never touched)")
            except OSError as err:
                # Cleanup failing must not mask the test's own result.
                print(f"\n(could not remove {TEST_STATE_PATH}: {err} -- safe to delete manually)")
    sys.exit(exit_code)
