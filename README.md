# Regulatory Scraper & Briefing Pipeline

An automated system monitoring Philippine regulatory bodies (BIR, IC, SEC) to deliver
concise, actionable regulatory briefings for MIGI/MILI (insurance) and MIBI
(brokerage) operations.

This system implements the architecture defined in `Regulatory-Scraper-Architecture-Foundation.md`
and `Regulatory-Scraper-Implementation-Handoff.md` (Architecture 3: Federated Source
Adapters with a Shared Core). Those two documents are the source of truth for *why*
the system is built this way; this README only covers *how to run it*.

## Structure

- `core/adapters/` — one adapter per regulator (BIR, IC, SEC). Each owns its own
  access path and parsing; none of them talk to each other or to the Shared Core
  directly.
- `core/detect.py`, `core/compose.py`, `core/notify.py`, `core/commit_state.py` —
  the regulator-agnostic Shared Core: Detect → Compose → Notify → Commit State.
- `core/state.py` — Issuance State persistence.
- `core/sheets_config.py` — Operational Configuration (active sources, recipients,
  notification schedule) and Business Context Configuration, read from a Google Sheet.
- `core/schedule.py` — decides, from the Sheet's schedule parameters and the last
  recorded run, whether a given invocation should run a check at all, and whether
  it's the business day's opening check.
- `core/notify_channels.py` — the real (SMTP email) notification channel.
- `models/issuance.py` — the shared `CandidateIssuance` / `BriefingRecord` data model.
- `main.py` — the entry point wiring all of the above together.

## Google Sheet Configuration

Everything below is meant to be edited by a non-technical user without a code
change (Foundation §3.2). Create a Sheet with these tabs:

**`Sources`** — one row per (Regulator, Category) monitoring unit:

| Regulator | Category | Active | Recipients |
|---|---|---|---|
| BIR | RMC | Y | tax@yourcompany.com |
| IC | IC-CL | Y | compliance@yourcompany.com |
| IC | IC-ADVISORY | N | legal@yourcompany.com |
| SEC | SEC-MC | Y | corpsec@yourcompany.com |

- `Active` (`Y`/`N`) controls whether that regulator/category actually runs this pass.
  If the Sheet isn't configured at all, every built-in adapter runs (fail-open —
  an unconfigured Sheet never silently disables monitoring).
- `Recipients` (comma-separated) is resolved per (Regulator, Category) first, then
  falls back to any recipients configured for that Regulator with no Category, then
  to the `NOTIFICATION_RECIPIENTS` env var.

**`Schedule`** — key/value rows controlling notification timing:

| Key | Value |
|---|---|
| BusinessDays | Mon,Tue,Wed,Thu,Fri |
| OpeningTime | 10:00 |
| PollingIntervalMinutes | 30 |
| Timezone | Asia/Manila |

Defaults (shown above) apply to any row that's missing. Note: the GitHub Actions
`schedule:` trigger itself is a fixed technical *ceiling* (see the workflow file) —
GitHub evaluates cron before any of this code runs, so it can't read the Sheet.
This table controls the *effective* schedule within that ceiling: `main.py` checks
these values against the last recorded run every time the workflow wakes up, and
no-ops (exits 0, not a failure) on wake-ups that don't match.

**`BusinessContext`** — profile, strategic initiatives, focus areas, etc. Read by
`get_business_context()`, but not yet consumed by anything — Assess (Phase 4) is
the intended consumer and isn't built yet (see below).

AI-based impact assessment (Assess, `core/assess.py`) and document archiving
(Archive, `core/archive.py`) are both implemented as best-effort steps: if either
is unconfigured or fails for any reason, its field(s) are simply marked
`UNAVAILABLE` in the briefing — the email still goes out immediately with
everything else intact, per the frozen fail-open behavior.

**Archiving = email attachment + a shared Drive archive.** Archive fetches each new issuance's document and the briefing email attaches it ("Archived Copy" column: "Attached" + filename). Limits: 8 MB per document, ~15 MB per email; over-limit files are flagged in the table and the Official Source link still works. A small Google Apps Script in the mailbox account (`docs/Drive-Attachment-Copier.gs`, hourly trigger) then files every attachment into Drive as `Regulatory Archive/<REGULATOR>/<TYPE>/` using the standard name `REGULATOR_TYPE_NUMBER.ext` (e.g. `BIR_RMC_RMC-No-61-2026.pdf`). So recipients know the archive exists, set the optional `ARCHIVE_FOLDER_URL` secret (the archive folder's Drive URL, with the folder shared to the recipients): every email then carries an "Open the Regulatory Archive" link. (An experimental upload path through an Apps Script web app, `docs/Drive-Archive-WebApp.gs` with `DRIVE_UPLOAD_URL`/`DRIVE_UPLOAD_TOKEN`, returns a per-file Drive link, but it needs the Workspace admin to allow web apps open to "Anyone" — blocked at Moneeinsure on 2026-10-07 — so it is unused. Service-account Drive upload was dropped on 2026-10-06: service accounts have no storage quota in a normal Drive folder.)

## Dashboard (Google Sheet)

The pipeline also writes a human-facing view into the same Sheet (`core/dashboard.py`,
Foundation §4.5). Issuance State stays the source of truth for what has been seen, and
dashboard writes are best-effort: if the Sheet can't be written, notifications and state
are unaffected.

| Tab | What it holds | Written by |
|---|---|---|
| `Briefings` | The full log, one row per emailed briefing. Columns A–N come from the scraper (date, regulator, type, number, title, **Review Priority** [the AI's urgency, not a final risk call], summary, AI impacts, suggested action, archived copy, source link). Columns **O–T are the team's**: Applicability (Yes/No/Partially), Impact/Risk, Required Action, Owner, Due Date, Status (For Assessment / Action Required / In Progress / Closed / Not Applicable). | Scraper: new rows only, with Status = For Assessment. Team: O–T. The scraper never edits an existing row. |
| `Health` | The **latest run only** (overwritten each run): run type, counts, per-source OK/FAILED/SKIPPED. No history, by design. | The pipeline, every real run |
| `Dashboard` | Five cards (For Assessment, Applicable/Open, High-Risk Open, Overdue, Due Soon), an **Action Required** table (max 20, most urgent first), and one scraper-health line with the archive link. All formulas. | `tools/setup_dashboard.py` |

**Workflow:** New regulation → *For Assessment* → team sets **Applicability**. *No* → done (it
drops off the dashboard). *Yes/Partially* → team fills Impact/Risk, Required Action, Owner, Due
Date and sets Status → *In Progress* → *Closed*.

**Definitions:** *Open* = Applicability Yes/Partially and Status not Closed/Not Applicable (a blank
Status counts as open). *For Assessment* = no Applicability chosen yet. *High-Risk Open* = Open and
Review Priority High. *Overdue* = Open with a Due Date before today. *Due Soon* = Open, due within 30
days. The Action Required table lists open and not-yet-assessed items: overdue first, then High
Review Priority, then earliest Due Date, then newest.

**Setup:** (1) the Sheet must be shared with the service account's `client_email` as **Editor**;
(2) Actions → **Setup Dashboard Tab** → Run workflow (set `demo` = `add` the first time to see sample
rows; expected cards with only the demo rows: 2 | 3 | 1 | 1 | 1; run again with `demo` = `remove` to
delete them). Re-running only deletes and recreates the `Dashboard` tab; it upgrades `Briefings` in
place (header row, dropdowns, hides the legacy "Needs Review" column) and never touches data rows.
The Briefings tab is now also where the team records its decisions — don't delete rows, and use the
Sheet's version history if something is changed by mistake. `tools/test_digest_email.py` sets
`DASHBOARD_DISABLED=1` so test replays never reach the real log.

## Setup (Local)

1. Install Python 3.11+.
2. `pip install -r requirements.txt`
3. Set the environment variables below as needed.
4. Run a check: `python main.py` (recurring check) or `python main.py --opening-run`
   (the business day's opening check — sends a Daily Monitoring Report if nothing
   new is found).

## Environment Variables / Secrets

| Variable | Required | Purpose |
|---|---|---|
| `SMTP_SENDER_EMAIL` | For real email delivery | Gmail/SMTP sending account. If unset, the system falls back to printing notifications to the console instead of emailing anyone. |
| `SMTP_SENDER_PASSWORD` | With the above | SMTP app password. |
| `SMTP_SERVER` / `SMTP_PORT` | No | Default `smtp.gmail.com` / `587`. |
| `NOTIFICATION_RECIPIENTS` | Fallback only | Comma-separated recipient list used when no Sheet-based recipient mapping is configured for a given regulator. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | For Sheet-based config | Path to a Google service account credentials file. If unset, Operational/Business Context Configuration falls back to defaults and env vars — the system does not fail, per the Foundation's "optional, no-op if unset" convention. |
| `SHEET_ID` | With the above | The spreadsheet ID containing a `Sources` tab (Regulator/Category/Recipients) and a `BusinessContext` tab. |
| `DRIVE_FOLDER_ID` | No longer used | Removed 2026-10-06 — archiving is now an email attachment (see above). Safe to delete this secret from GitHub. |
| `ARCHIVE_FOLDER_URL` | Optional | Drive URL of the shared archive folder (`https://drive.google.com/drive/folders/<ID>`). Shown as an "Open the Regulatory Archive" link in every email so recipients know where documents are kept. Share the folder with the recipients. Omitted if unset. |
| `DRIVE_UPLOAD_URL` / `DRIVE_UPLOAD_TOKEN` | Unused | Experimental per-file Drive link via an Apps Script web app; needs the admin to allow "Anyone" access. Leave unset. |
| `SCRAPER_PROXY_API_KEY` | For IC and SEC | insurance.gov.ph and sec.gov.ph both block requests from GitHub Actions' (and similar cloud/datacenter) IP ranges specifically (confirmed via real runs/checks) — for both their listing pages *and* individual document URLs. A [ScraperAPI](https://www.scraperapi.com/) key (or compatible service using the same `?api_key=&url=` convention) routes those requests around the block. Without it, IC/SEC adapters will fail loudly on every run rather than silently returning nothing, and IC/SEC document archiving will fail open (marked `UNAVAILABLE`) instead of uploading anything. Listing pages are restricted to the opening check only (`OPENING_CHECK_ONLY` on their adapters) to stay within ScraperAPI's free tier (~1,000 requests/month); document archiving is not opening-check-only, since it only fires per genuinely new issuance rather than once/category/day — watch actual usage against the free tier if IC/SEC produce a lot of new issuances in a short span (e.g. a large backlog catch-up). BIR doesn't need this at all. |
| `ANTHROPIC_API_KEY` | For AI impact assessment | Powers the Assess step (`core/assess.py`, Phase 4) — calls Claude Haiku (Anthropic API) to produce the executive summary, MIGI/MILI/MIBI impact, risk level, and suggested action for each new issuance. Reads business priorities from the Sheet's `BusinessContext` tab (falls back to a generic default if that tab is empty). If unset, or the call fails for any reason, those fields are simply marked `UNAVAILABLE` in the briefing — the email still goes out immediately with all other information intact, per the frozen fail-open behavior. Get a key at [console.anthropic.com](https://console.anthropic.com) (requires billing/credits — a one-time free trial credit is often available on new accounts, but check Billing → Credit grants for any expiration). Switched from OpenAI → briefly Groq → Anthropic on 2026-09-03 after the OpenAI project ran out of credit; Jas preferred Claude's summary quality and had spare Anthropic credit available. |

## Running Tests

```
pytest
```

## GitHub Actions

`.github/workflows/compliance_monitor.yml` is the only scheduled workflow. It runs
the opening check once per business day and recurring checks every 30 minutes
during business hours, identifying the opening run by which cron schedule actually
matched (not by comparing wall-clock time, since scheduled workflow timing is not
guaranteed to the minute).
