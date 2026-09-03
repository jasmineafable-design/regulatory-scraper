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

AI-based impact assessment (Assess) is intentionally not implemented yet — every
briefing's AI-derived fields are stubbed as `UNAVAILABLE`, per the approved
fail-open behavior. Google Drive document archiving is also not implemented yet.
Both are later, deliberately deferred phases (see the Handoff document's roadmap),
not oversights in this consolidation.

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
| `SCRAPER_PROXY_API_KEY` | For IC and SEC | insurance.gov.ph and sec.gov.ph both block requests from GitHub Actions' (and similar cloud/datacenter) IP ranges specifically (confirmed via real runs/checks). A [ScraperAPI](https://www.scraperapi.com/) key (or compatible service using the same `?api_key=&url=` convention) routes those requests around the block. Without it, IC/SEC adapters will fail loudly on every run rather than silently returning nothing. Both are restricted to the opening check only (`OPENING_CHECK_ONLY` on their adapters) to stay within ScraperAPI's free tier (~100 requests/month) across IC-CL + SEC-MC + SEC-Resolution (~66/month combined). BIR doesn't need this. |
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
