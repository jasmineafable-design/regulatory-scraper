import json
import logging
import os
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class SheetsConfigReader:
    """
    Reads Operational Configuration and Business Context Configuration from a
    Google Sheet (§3.2/§3.5), so non-technical users can change what's monitored,
    who's notified, the notification schedule, and the business context that
    later bounds AI assessment (Phase 4 — not built in this consolidation pass)
    — without a code change.

    Consolidates the two competing Sheets-reading approaches found during the
    implementation review (a published-CSV reader and a service-account/gspread
    reader) onto the gspread/service-account approach, matching the prior
    system's convention (GOOGLE_SERVICE_ACCOUNT_JSON secret).

    Gates itself quietly: if no service account or spreadsheet ID is configured,
    every method returns an empty result / documented default rather than
    raising, so the system keeps running on env-var/hardcoded fallbacks (§9 of
    the Handoff — this mirrors the prior system's optional, no-op-if-unset
    Sheets/Drive integration).

    Expected tabs:
    - 'Sources': one row per (Regulator, Category) monitoring unit — columns
      Regulator | Category | Active | Recipients. Drives both which
      regulator/category pairs actually run (get_active_sources) and who gets
      notified for each (get_recipient_matrix) — §3.2.
    - 'BusinessContext': profile, strategic initiatives, focus areas, etc.,
      consumed by Assess (Phase 4, not yet built).
    - 'Schedule': key/value rows (Key | Value) — BusinessDays, OpeningTime,
      PollingIntervalMinutes, Timezone — §3.2's notification schedule
      parameters.
    """

    def __init__(self, service_account_json: Optional[str] = None, spreadsheet_id: Optional[str] = None):
        self.service_account_json = service_account_json or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        self.spreadsheet_id = spreadsheet_id or os.getenv("SHEET_ID")
        self._gc = None

        if not self.service_account_json or not self.spreadsheet_id:
            logger.info("Sheets config not set (GOOGLE_SERVICE_ACCOUNT_JSON/SHEET_ID unset) — using defaults/env vars only.")
            return

        try:
            import gspread  # imported lazily so the dependency is optional at runtime

            # GOOGLE_SERVICE_ACCOUNT_JSON is documented (README) as "paste the
            # entire contents of the downloaded JSON key file" into the GitHub
            # secret -- i.e. the raw JSON text itself, not a path to a file on
            # disk (there is no such file in the GitHub Actions runner).
            # Detect which one we actually got: valid JSON -> parse it and
            # authenticate from the dict; otherwise, fall back to treating it
            # as a real file path (keeps local/dev usage with an actual
            # key-file path working too).
            try:
                credentials_dict = json.loads(self.service_account_json)
                self._gc = gspread.service_account_from_dict(credentials_dict)
            except json.JSONDecodeError:
                self._gc = gspread.service_account(filename=self.service_account_json)
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Sheets API: {e}")
            self._gc = None

    def _worksheet(self, name: str):
        if not self._gc:
            return None
        try:
            return self._gc.open_by_key(self.spreadsheet_id).worksheet(name)
        except Exception as e:
            logger.error(f"Failed to open worksheet '{name}': {e}")
            return None

    def get_sources_config(self) -> List[Dict[str, Any]]:
        """Rows of the 'Sources' tab: Regulator | Category | Active | Recipients."""
        sheet = self._worksheet("Sources")
        if not sheet:
            return []
        return sheet.get_all_records()

    def get_active_sources(self) -> Optional[Set[Tuple[str, str]]]:
        """(Regulator, Category) pairs marked Active in the Sources tab.

        Returns None — rather than an empty set — when the Sheet isn't
        configured/reachable, meaning "no filter configured, treat everything
        as active." This fail-open default matters: an unconfigured Sheet must
        never silently disable all monitoring (§3.4 principle 2/§3.8).
        """
        rows = self.get_sources_config()
        if not rows:
            return None

        active: Set[Tuple[str, str]] = set()
        for row in rows:
            regulator = str(row.get("Regulator") or "").strip().upper()
            category = str(row.get("Category") or "").strip().upper()
            active_flag = str(row.get("Active") or row.get("Active Y/N") or "").strip().upper()
            if regulator and category and active_flag in ("Y", "YES", "TRUE", "1"):
                active.add((regulator, category))
        return active

    def get_recipient_matrix(self) -> Dict[Tuple[str, str], List[str]]:
        """(Regulator, Category) -> recipient list, from the Sources tab.

        Keyed by category as well as regulator (§3.2 requires recipients be
        configurable "per regulator/category", not just per regulator) — a row
        with an empty Category still keys under ("REGULATOR", ""), which
        EmailNotificationChannel treats as a regulator-wide fallback.
        """
        rows = self.get_sources_config()
        matrix: Dict[Tuple[str, str], List[str]] = {}
        for row in rows:
            regulator = str(row.get("Regulator") or "").strip().upper()
            category = str(row.get("Category") or "").strip().upper()
            recipients_raw = str(row.get("Recipients") or "")
            recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
            if regulator and recipients:
                matrix.setdefault((regulator, category), []).extend(recipients)
        return matrix

    def get_schedule_config(self) -> Dict[str, str]:
        """Key/value rows of the 'Schedule' tab, merged over documented defaults
        (Foundation §3.2: business-day calendar default Mon-Fri, opening-check
        time default 10:00, recurring polling interval default 30 minutes).

        Falls back entirely to defaults if the Sheet or tab isn't configured —
        never raises, per the same fail-open-on-config convention as the rest
        of this reader.
        """
        defaults = {
            "BusinessDays": "Mon,Tue,Wed,Thu,Fri",
            "OpeningTime": "10:00",
            "PollingIntervalMinutes": "30",
            "Timezone": "Asia/Manila",
        }
        sheet = self._worksheet("Schedule")
        if not sheet:
            return defaults
        try:
            rows = sheet.get_all_records()
            overrides = {
                str(r.get("Key")).strip(): str(r.get("Value")).strip()
                for r in rows
                if r.get("Key") and r.get("Value")
            }
            return {**defaults, **overrides}
        except Exception as e:
            logger.error(f"Failed to read Schedule tab, using defaults: {e}")
            return defaults

    def get_business_context(self) -> List[Dict[str, Any]]:
        """Rows of the 'BusinessContext' tab (profile, initiatives, focus areas, etc.).

        Consumed by Assess (Phase 4), which is not built in this consolidation pass —
        this method exists so the plumbing is in place ahead of that phase.
        """
        sheet = self._worksheet("BusinessContext")
        if not sheet:
            return []
        return sheet.get_all_records()
