# Regulatory Scraper — Implementation Review & Consolidation Plan

**Status:** Historical record. This review preceded the consolidation pass; the plan it describes has since been executed. See the consolidation summary (delivered in chat, and this repo's current `core/`, `models/`, `main.py`, and `tests/`) for what was actually built. Retained here as the audit trail for why the codebase looks the way it does.

**Scope of this review:** `C:\Users\RSIPH0012\Claude\regulatory-scraper-main`, as it existed before consolidation — the result of implementation work done outside this session (presumably across more than one Gemini session, based on the evidence below).

---

## 1. Implementation Trees Identified

Three separate, non-integrated implementation attempts existed in this one repository, plus one internal split inside the largest of the three:

**Tree A — `src/`.** A full parallel implementation: `src/adapters/{base,bir,ic,sec}.py`, `src/pipeline/orchestrator.py`, `src/storage/state_store.py`, `src/notifier/email_notifier.py`, `src/config/sheets_config.py`, entry point `src/main.py` (root `main.py` re-exports this). **This was the tree both GitHub Actions workflows actually executed.**

**Tree B — `core/`.** A second full parallel implementation, itself split into two incompatible generations that were never reconciled:
- **B1 (older generation):** `core/models.py`, `core/base_adapter.py`, `core/notifier.py`, `core/adapters/{bir,ic,sec}_adapter.py`. Used its own `CandidateIssuance`/`BriefingRecord` definitions that did not match the frozen content contract (§3.2/§5.2 of the Foundation).
- **B2 (newer generation):** `core/detect.py`, `core/compose.py`, `core/notify.py`, `core/commit_state.py`, `core/state.py`, `core/config.py`. Used `models/issuance.py` (see Tree C) and explicitly cited Foundation section numbers in its own docstrings (§3.6, §3.7, §5.2, §13). This was the most architecturally faithful code in the repository.
- Shared, tree-agnostic utilities also lived under `core/`: `http_client.py`, `parsing.py`, `exceptions.py`, `logger.py`, `google_sheets.py` — none tied to B1 or B2 specifically.

**Tree C — loose top-level modules.** `models/issuance.py` and `state/manager.py`, invoked only by an orphaned entry point, `run_pipeline.py`. `models/issuance.py` was B2's data model. `state/manager.py` was a *third*, independent state-persistence implementation.

**A fourth, broken artifact:** `run_pipeline.py` imported bare functions (`detect_new_issuances`, `compose_briefing`, `send_notification`) that no longer existed in `core.detect`/`core.compose`/`core.notify` (which only exported classes) — would have failed with `ImportError` if run.

---

## 2. Canonical Implementation Determination

**Tree B2 plus `models/issuance.py` was chosen as the canonical implementation core.** Three reasons: (1) `models/issuance.py` matched the Foundation's §5.1/§5.2 data model almost field-for-field; (2) B2's `detect.py`/`compose.py`/`notify.py`/`commit_state.py` already implemented the exact frozen behaviors (baseline exclusion, §3.7 branching, notify-before-commit); (3) B2 already had passing end-to-end tests (`tests/test_phase1_core.py`) exercising the real chain, not mocks across the defective seam.

Tree A was the tree actually wired to production but was judged the weakest architecturally: no content contract, no baseline mechanism, a notifier whose method names didn't match what the orchestrator called, no explicit Fetch→Validate→Detect structure.

**What still needed to be built:** B2 had no adapters that actually fetched anything, and no orchestrator/entry point. Adapters had to be salvaged from B1 (real parsing, fake fetch) and Tree A (real fetch, at least for BIR) and rebuilt against `models.issuance.CandidateIssuance`.

---

## 3. File-by-File Classification (as it stood pre-consolidation)

See the original analysis for the full three-way Keep/Modify/Move-Merge/Delete table. **Outcome after execution:** every file marked "Delete" was removed; every file marked "Keep as-is" was verified and kept; every file marked "Keep but modify" or "Move/Merge" was rebuilt into the current `core/adapters/*`, `core/notify_channels.py`, `core/sheets_config.py`, and `main.py`. One item not caught by the original file-by-file pass — `core/adapters/base_adapter.py`, which imported the since-deleted `core.models` — was discovered and fixed during consolidation.

---

## 4. Dependency Map (historical — pre-consolidation)

**Production entry point:** `main.py` (root), which wired to Tree A (`src.pipeline.orchestrator.RegulatoryPipeline`, only `SECAdapter` instantiated, `src.notifier.email_notifier.EmailNotifier`) — the weakest-aligned tree, yet the one both workflows actually executed. The most architecturally correct code (the entire B2 chain) was fully built, tested, and completely disconnected from any entry point — dead code purely because nothing invoked it. This mismatch between "what's correct" and "what's wired" was the central finding of this review and the reason a consolidation pass (rather than a redesign) was the right next step.

---

## 5. Deviations From the Frozen Architecture (as found — all resolved in consolidation)

| # | Severity | Deviation | Resolution |
|---|---|---|---|
| 1 | Critical | Orchestrator called notifier methods (`send_immediate_briefing`, `send_daily_monitoring_report`) that didn't exist on `EmailNotifier` — guaranteed crash on real data. | Retired; `core/notify.py`'s `dispatch()` now runs against the real `EmailNotificationChannel`. |
| 2 | Critical | Live code wrote `data/processed_state.json`; workflow cache only preserved `state/seen_issuances.json` — state didn't survive between runs. | `core/state.py` (writing to the cache-matched path) is now canonical. |
| 3 | Critical | No Compose step in the live path; notifier emailed raw regulator/title/link only — no content contract. | Everything now routes through `core/compose.py`. |
| 4 | Critical | Both SEC adapters targeted the blocked `www.sec.gov.ph` instead of the documented mirror. | Canonical SEC adapter now targets `appointment.sec.gov.ph`. |
| 5 | High | BIR/IC adapters returned one hardcoded fake record each; real parsing logic existed but was never invoked. | Adapters rebuilt with real HTTP fetch feeding the existing parsers. |
| 6 | High | `main.py` instantiated only `SECAdapter()`; BIR/IC were commented out. | New `main.py` wires all three regulators. |
| 7 | High | `--is-opening-run` was passed by the workflow but never read by `main.py` — the Daily Monitoring Report branch never executed. | New entry point accepts `--opening-run` via `argparse` and acts on it. |
| 8 | High | An unapproved Slack/webhook channel (`core/notifier.py`, `SLACK_WEBHOOK_URL`) existed alongside email. | Resolved by removal — see §7 below and the consolidation summary. |
| 9 | Medium | Two competing scheduled workflows (`scraper.yml` and `compliance_monitor.yml`) ran the same entry point independently. | `scraper.yml` deleted; `compliance_monitor.yml` is the only workflow. |
| 10 | Medium | Opening-run identification used fragile `$CRON_HOUR`/`$CRON_MIN` wall-clock string matching. | Replaced with `github.event.schedule` identity matching. |
| 11 | Medium | `requirements.txt` was missing `gspread`/Google API client. | Added `gspread` and `google-auth`. |
| 12 | Low | `run_pipeline.py` had broken imports; orphaned. | Deleted. |
| 13 | Low | `README.md` was incomplete. | Rewritten to describe the consolidated structure. |

---

## 6. Prioritized Implementation Backlog

All eleven tasks in the original backlog (retire non-canonical trees; fix SEC's URL; wire real fetch into BIR/IC; build the real notification channel; build the real orchestrator; fix opening-run identification; confirm state persistence; wire baseline handling; decide on one config-reading approach; correct `requirements.txt`; rewrite `README.md`) were completed during consolidation, in that order, respecting the stated dependencies.

---

## 7. Decisions Requiring Approval — Resolution

The one item this review flagged as a genuine scope question — the Slack/webhook channel (`core/notifier.py`, plus the `SLACK_WEBHOOK_URL` secret already wired into `compliance_monitor.yml`) — was resolved during consolidation by **removal**, on the grounds that nothing in the frozen Foundation or Handoff mentions any channel besides email, and the safer default under "do not introduce architecture changes without approval" is to drop scaffolding that was never approved rather than keep it live. This resolution is called out explicitly in the consolidation summary for confirmation, since it is a judgment call made on your behalf during repair rather than something you affirmatively chose.

---

## 8. Final Answers (as originally given — confirmed accurate in hindsight)

**Canonical tree:** B2 (`core/detect.py`, `compose.py`, `notify.py`, `commit_state.py`, `state.py`, `config.py`) plus `models/issuance.py`, with adapters rebuilt against that model — confirmed correct; this is exactly what now exists in the repo.

**Salvage vs. rebuild:** Salvage — confirmed correct; the consolidation reused the real fetch/parse bodies from both adapter trees and the SMTP logic from `EmailNotifier` rather than writing any of that from scratch.

**Reuse estimate:** The original 55–65% estimate held up well in practice — the deterministic core, state, and utility modules were kept essentially untouched; only the adapters, notification channel, config reader, and entry point needed real rebuilding.

**Hidden architectural risks identified, and how consolidation addressed them:**
1. *Mock-masked wiring defects* — addressed by verifying the rebuilt pipeline both via `pytest` and via a real (unmocked, monkeypatched-at-the-network-boundary-only) end-to-end dry run during consolidation, specifically to avoid re-hiding a defect behind component-level mocks.
2. *Multiple implementation attempts accumulating across sessions* — addressed structurally: exactly one implementation of each component now exists, with the obsolete trees deleted rather than left dormant.
3. *Duck-typed model classes silently overlapping* — addressed: `models/issuance.py` is now the only model module in the repository; `core/models.py` was deleted.
