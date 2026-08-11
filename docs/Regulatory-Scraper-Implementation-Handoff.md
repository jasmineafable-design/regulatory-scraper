# Regulatory Scraper — Implementation Handoff Document

**Purpose of this document:** this is a complete, self-contained handoff for whoever implements this system next. You should be able to start building from this document alone. It incorporates a companion document — the **Architecture Foundation** — which is frozen and authoritative; this document restates it in full so nothing is lost if only one file is read, but the Foundation document is the source of truth if the two ever appear to disagree (they shouldn't; this is a consolidation, and both were finalized together).

**Status:** Architecture and foundation frozen. Planning complete. Consolidation pass complete — see `Regulatory-Scraper-Implementation-Review.md` and the consolidation summary for what was built against this document.
**Owner:** Jas (jasmine.afable@moneeinsure.com.ph)
**Prior system:** an existing working system ("Regulatory Scraper," formerly "BIR Tax Update Auto Notif") already monitors BIR, IC, and SEC end-to-end. This handoff describes a reliability- and product-focused redesign of that system — some adapter-level knowledge (regulator access quirks, identifier formats) already exists and should be reused, not rediscovered (see §13).

---

## 1. Executive Summary

Moneeinsure (an insurance group comprising MIGI, a general/non-life insurance underwriter; MILI, a life insurance underwriter; and MIBI, an insurance brokerage) needs to know promptly whenever the Bureau of Internal Revenue (BIR), the Insurance Commission (IC), or the Securities and Exchange Commission (SEC) publish a new regulatory issuance that could affect the group's business.

The system's job is not "scrape three websites." The system's job is to produce a **concise, actionable regulatory briefing** for each new issuance — something a process owner can read in under a minute and understand what happened, whether it matters to MIGI/MILI, whether it matters to MIBI, how urgent it is, and what to do about it — without needing to open the source document. Scraping, state tracking, AI assessment, document archiving, and configuration are all in service of producing that briefing reliably. None of them is the product in its own right.

As the business changes — new strategic initiatives, new products, new regulatory focus areas — the system must be able to adapt by having a non-technical user update configuration, not by someone rewriting code.

## 2. Approved Architecture: Architecture 3 — Federated Source Adapters with a Shared Core

**Shape:** each regulator (BIR, IC, SEC, and any future regulator) is implemented as a fully independent **adapter**, responsible only for retrieving and validating content from that regulator's official source. All adapters feed into one **shared core** that is completely regulator-agnostic and owns everything from "is this issuance new" through "has it been delivered and recorded."

**Why this was chosen over the alternatives considered:**

- *Unified Sequential Pipeline* (one monolithic pass for every source) is simpler, but isolation between regulators is a matter of internal coding discipline rather than structure.
- *Decoupled Stage Pipeline with Durable Per-Issuance State* scales better to high volume and multiple operators, but was judged disproportionate to the system's actual current scale, and introduces a real risk that issuances could sit waiting on a stalled stage instead of being notified promptly.

Architecture 3 formalizes an isolation boundary that already exists in reality: BIR, IC, and SEC each have genuinely different access behavior (IC blocks scripted requests from cloud/datacenter IP ranges; SEC's main site blocks non-browser traffic entirely and must be reached through a mirror subdomain; BIR is directly accessible). Naming that boundary structurally, while keeping the downstream briefing logic simple and shared, satisfies the frozen foundation without adding complexity beyond what the system actually needs.

**Do not revisit this choice.** If an implementation decision appears to conflict with the Foundation, surface the conflict explicitly rather than redesigning around it.

## 3. Frozen Foundation

This section restates the Architecture Foundation document in full. See that document for the same content as the standalone authoritative reference.

### 3.1 System Goals

1. **Reliability** — every new issuance published through BIR's, IC's, and SEC's official sources must be detected and its notification delivered promptly, with no silent failure. "Promptly" means: each new issuance is reported immediately upon detection, on whichever monitoring cycle finds it — never held for a batch or for the next day's opening check.
2. **Actionability** — every Regulatory Briefing must let a process owner understand relevance and required action in under a minute, without opening the source document, via the minimum content contract (§3.2).

Secondary goal: operable by a single part-time maintainer; adaptable to business change through configuration alone, without code changes.

### 3.2 Functional Requirements

Every Regulatory Briefing must contain, at minimum: issuance number/title, executive summary, insurance entity impact (MIGI/MILI), brokerage entity impact (MIBI), risk/priority level, suggested action, link to the archived document, link to the official regulator source. Any field that cannot be produced must be explicitly flagged as unavailable — never silently omitted, never presented as if the briefing were complete when it isn't.

Non-technical-editable configuration: business context (profile, strategic initiatives, products/services, business activities, regulatory focus areas, current topics, custom evaluation criteria); recipients per regulator/category; notification schedule parameters (business-day calendar, default Monday–Friday; opening-check time, default 10:00 AM; recurring polling interval, default every 30 minutes).

Notification types: Daily Monitoring Report and Regulatory Briefing — fully specified in §3.7.

### 3.3 Constraints

- One part-time maintainer; no dedicated ops/SRE support.
- Real, already-occurred incidents define the actual risk surface: an unrelated domain migration silently broke Gmail-based email sending; a bug once mis-recorded a failed fetch as "genuinely nothing new," nearly causing a backlog flood on first activation of a category; IC blocks datacenter/cloud IP ranges; SEC's main site blocks non-browser traffic and is instead reached via a mirror subdomain (`appointment.sec.gov.ph`).
- Must operate within free-tier budgets throughout. This bears directly on the recurring polling interval: a shorter interval means more fetches, and IC specifically requires a scraping proxy whose free tier is limited (historically ~1,000 requests/month) — the actual configured interval for IC may need to be coarser than for BIR/SEC, or the whole system's interval may need to be chosen with this in mind. This is implementation guidance (§12), not a fixed number — the default of "every 30 minutes" stated in §3.2 is a default, not an immovable requirement, and should be tuned against actual proxy usage once implemented.
- GitHub Actions' own scheduled-workflow timing is not guaranteed to the minute — documented delays of 5–30 minutes are normal, and 30–60+ minute delays are possible under load (this has reportedly worsened through 2026). "Promptly" is bounded by whichever scheduling platform is actually chosen; if tighter timing is later required, an external scheduler calling the workflow's dispatch API directly is the documented fix, rather than relying on GitHub's own cron queue.
- The prior system already runs on Google Workspace and GitHub-based tooling — existing environment, not a mandated future stack.
- Each regulator site has distinct, previously-unknown-until-encountered access restrictions — an ongoing discovery problem, not solved once and forgotten.
- No dedicated monitoring/alerting infrastructure exists or should be built new.

### 3.4 Design Principles

1. Detection over prevention, where prevention isn't achievable.
2. Fail loud, never silent.
3. Isolate failure domains.
4. Reuse existing infrastructure before building new infrastructure.
5. Configuration changes deserve the same traceability as code changes.
6. Complexity is proportional to actual, not anticipated, scale.
7. Duplicate notifications are acceptable; silent data loss is not.
8. All scheduled runs must be idempotent.
9. Positive evidence that the system is operating is required once per business day, produced by the outcome of that day's opening check — either the Daily Monitoring Report (nothing found) or the Regulatory Briefing itself (something found). This is distinct from genuine failure detection (§3.8) and must not be conflated with it.
10. AI is advisory only — never determines whether an issuance exists, is reported, or triggers notification; those are deterministic.
11. Business-context configuration, recipients, and notification schedule parameters must all be non-technical-user-editable.
12. Business-facing notifications and operational/maintainer diagnostics are distinct concerns and must not be merged. Adapter failures, degraded sources, and notification-channel failures are surfaced exclusively through existing fail-loud infrastructure behavior and logs — a maintainer concern, never through Daily Monitoring Report or Regulatory Briefing content.

**Approved AI/best-effort failure decision (frozen):** if AI assessment or any best-effort field (e.g., the archive link) fails, the system still delivers the Regulatory Briefing using all available deterministic information, with missing sections explicitly identified. Never silently omit required analysis; never present an incomplete briefing as complete.

### 3.5 Source of Truth

Four authoritative records — how each is stored is an implementation decision, not a property of what's authoritative:

- **Issuance State** — which issuances are already known/processed.
- **Operational Configuration** — active sources/categories, recipients per regulator/category, and notification schedule parameters.
- **Business Context Configuration** — profile, strategic initiatives, products/services, business activities, regulatory focus areas, current topics, custom evaluation criteria.
- **Application Logic** — the fetch/validate/detect/assess/compose/notify code.

**No fifth record (a persistent failure-history or "health" store) is currently justified.** This was deliberately considered and rejected: the Daily Monitoring Report's source-health signal refers only to the outcome of the day's opening check — a point-in-time result — and needs no retained history to produce. If real operational experience later shows historical tracking is valuable, it can be introduced then; it is explicitly not part of this architecture now.

Only content from an official regulator publication channel is authoritative; a mirror or proxy is a sanctioned access path to that content, never an independent source of truth. Any dashboard, log, or archive is a rendering of the four records above, never a fifth store.

### 3.6 Critical Path

One execution flow, invoked repeatedly on a single recurring schedule (an opening check at a configured daily time, then recurring checks at a configured interval for the rest of the business day):

**Fetch → Validate → Detect → Assess → Compose → Notify → Commit State**

- **Fetch** — retrieve a response from, or through a sanctioned access path to, an official regulator source.
- **Validate** — confirm genuine content, not a CAPTCHA, block page, error, or malformed/empty response. A validation failure is a failure, never reinterpreted as "no new issuances."
- **Detect** — deterministically compare validated content against Issuance State. A category being baselined for the first time (§3.7) is excluded from "new" here by definition — its backlog is recorded as known, not treated as a flood of new issuances.
- **Assess** — AI-advisory, bounded by Business Context Configuration. May fail without halting the item.
- **Compose** — assemble the content-contract fields; explicitly flag anything that couldn't be produced.
- **Notify** — see §3.7 for exactly what gets sent and when.
- **Commit State** — mark an issuance processed only after Notify has succeeded for it.

State only advances once delivery is confirmed, so a failure up to and including Notify never causes an issuance to be silently lost — the next check detects it as still-new and retries.

### 3.7 Notification Strategy

Two business-facing notification types — mutually exclusive outcomes of the same check, not two subsystems:

**Daily Monitoring Report** — sent only when the business day's opening check (default weekdays, default 10:00 AM, both configurable) finds zero new issuances. States this explicitly and sets the expectation that monitoring continues and any newly detected issuance will generate its own immediate notification. Contains no operational diagnostics and no per-source health detail beyond the fact that nothing new was found — it's a business-perspective content statement, not a system-status report.

**Regulatory Briefing** — sent immediately, per issuance, whenever any check that day (opening or later) detects something new, containing the full content contract (§3.2). If the opening check finds one or more new issuances, the Briefing(s) go out and no Daily Monitoring Report is sent that day.

**Every later check:** finds something → Regulatory Briefing, immediately. Finds nothing → no notification at all — expected, not a gap.

**Deliberately excluded:** no separate heartbeat notification, no per-cycle status message, no persistent cross-cycle health record. A source failing validation on the opening check is only reflected in whether anything new was found that morning — it is never separately named or diagnosed in either business-facing notification. Operational issues are a maintainer concern (§3.8), by deliberate design, not an oversight.

**Accepted trade-off:** because the opening check's health signal is a single point-in-time result, a source that's genuinely flaky — failing most checks but succeeding at the moment of the opening check — will not be flagged as degraded that day. Deliberately accepted, the direct consequence of not retaining failure history.

### 3.8 Failure Philosophy

- Fail closed on state, fail open on delivery.
- Prefer a duplicate notification over any risk of silent loss — safe because runs are idempotent.
- Correlated failures should read as one legible story, not scattered alarms.
- **Business-facing content evidence and genuine failure detection are two distinct signals and must not be collapsed into one.** The Daily Monitoring Report / Regulatory Briefing pair proves to the business that the system engaged with real content once per day — but both travel through the same notification channel, so their absence is not independently proof of failure (if that channel itself is broken, both would be silent for the same reason). The genuinely independent signal is the existing infrastructure-level fail-loud mechanism — letting an execution error fail the scheduled job itself, so the scheduling platform's own native failure notification fires, through a channel that doesn't depend on email at all. **This mechanism must remain in place underneath the notification strategy; it is not replaced by it.**
- Operational issues surface through that same infrastructure-level mechanism and through logs — a maintainer concern, never merged into business-facing content.
- Silent *data* loss and silent *quality* loss are both failures.
- **Known, accepted residual gap:** none of the above detects the scheduling trigger never firing at all (as opposed to firing and failing) — there's no run, so there's nothing to fail loudly about. Accepted, consistent with reuse-existing-infrastructure and proportional-complexity — closing it fully would need dedicated new monitoring infrastructure not currently justified.

### 3.9 Non-Goals

- Not a substitute for professional or legal judgment.
- Not an automatic legal-applicability determination system.
- Not a full document management system — archiving is convenience, not records-management.
- Not a real-time alerting system — scheduled cadence, not instant latency.
- Not a general anti-bot circumvention platform.
- Not an operational monitoring/observability platform for business recipients — deliberately excluded, revisitable only with real evidence of need.
- Not a historical or trend-based source-health tracker — point-in-time only, by design.
- AI output is not guaranteed exhaustive or error-free, and is bounded by the quality of Business Context Configuration supplied — thin or stale configuration produces generic output, an expected limitation, not a defect.

---

## 4. Components

### 4.1 Regulator Source Adapters (one per regulator: BIR, IC, SEC; extensible)

**Responsibilities:** Fetch from the official source (directly, or through a sanctioned access path); Validate that the response is genuine; normalize into the shared Candidate Issuance model (§5).

**Owns exclusively:** the specific access path and any workaround it requires; parsing/extraction logic for that regulator's content structure; extraction of a stable identifier per issuance in that regulator's own numbering convention (see §13 for what's already known per regulator).

**Inputs:** its own configuration (which categories are active). **Outputs:** zero or more Candidate Issuance records tagged with a validation status, or an explicit adapter-level failure signal. **Interactions:** invoked by the Orchestrator; hands output to the Shared Core; never calls another adapter or any Shared Core step directly.

### 4.2 Shared Core

Regulator-agnostic. Owns everything downstream of "we have a normalized candidate":

- **Detect** — deterministic comparison against Issuance State, respecting the baseline exclusion (§3.6).
- **Assess** — AI-advisory, reads Business Context Configuration, degrades gracefully per the frozen decision.
- **Compose** — assembles the content contract, flags what's missing.
- **Notify** — implements the notification strategy in §3.7 exactly: per-issuance Regulatory Briefing whenever anything is found on any check; the Daily Monitoring Report only when the opening check finds nothing.
- **Commit State** — marks an issuance processed only after Notify succeeds for it.

**Inputs:** normalized candidates from any adapter; Issuance State; Business Context Configuration; Operational Configuration (recipients, schedule). **Outputs:** delivered notifications; updated Issuance State. **Interactions:** invoked by the Orchestrator once per adapter's output; never invokes an adapter.

### 4.3 Orchestrator

The scheduler-triggered entry point. Reads Operational Configuration to determine active adapters/categories and the notification schedule. Invokes each active adapter in isolation — one adapter's failure must not prevent others from running, nor prevent the Shared Core from processing whatever the others did produce. Identifies whether the current invocation is the business day's opening check (by which schedule trigger fired — a distinct opening-time entry vs. the recurring interval — not by fragile wall-clock comparison, since scheduling platforms are not minute-precise) and passes that context into the Shared Core so Notify can apply the correct branching from §3.7. Lets any adapter or Shared Core execution error propagate so the scheduling platform's own native failure notification fires (§3.8) — this is not caught and swallowed.

### 4.4 Archive (best-effort side output)

Stores a retrievable copy of the source document and produces the content-contract archive link. Explicitly best-effort and non-authoritative (§3.9: not a document management system) — its failure is handled exactly like an Assess failure: the field is flagged unavailable, and the briefing is delivered anyway.

### 4.5 Dashboard / Log (human-facing view, optional)

A rendering of Issuance State, configuration, and application logs for human inspection. Never an independent store of any fact — if it ever disagrees with Issuance State, Issuance State is correct by definition.

*(There is no separate Heartbeat/Evidence component. Positive evidence of execution is produced by Notify itself, via whichever of the two business-facing outputs the opening check yields — see §3.4 principle 9 and §3.7.)*

---

## 5. Normalized Data Model

### 5.1 Candidate Issuance (adapter output → Shared Core input)

| Field | Description |
|---|---|
| `source_regulator` | BIR / IC / SEC / future. |
| `source_category` | The specific issuance category within that regulator. |
| `issuance_identifier` | Stable identifier in the regulator's own numbering convention — used by Detect for dedup. |
| `issuance_title` | Human-readable title/label. |
| `publication_date` | If reliably extractable; optional. |
| `source_url` | Official regulator link — required content-contract field. |
| `raw_content_reference` | Pointer to the fetched raw content, for Assess and Archive. |
| `fetched_at` | Timestamp of this fetch attempt. |
| `validation_status` | genuine / blocked / error / malformed. Only `genuine` proceeds past Validate. |

### 5.2 Briefing Record (Compose output → Notify input → Issuance State entry)

| Field | Description |
|---|---|
| `issuance_identifier`, `source_regulator`, `source_category`, `issuance_title` | Carried from the Candidate Issuance. |
| `executive_summary`, `insurance_entity_impact`, `brokerage_entity_impact`, `risk_priority_level`, `suggested_action` | AI-advisory; each may be explicitly marked unavailable. |
| `archived_document_link` | Best-effort; may be marked unavailable. |
| `official_source_link` | Deterministic, from `source_url` — should essentially never be missing. |
| `completeness_status` | complete / degraded. |
| `composed_at`, `notified_at`, `committed_at` | Timestamps; `committed_at` is what Detect checks on future runs. |

**Daily Monitoring Report has no equivalent per-issuance record** — it's a simple, directly-composed message (date, opening-check time, "no new issuances found," expectation-setting text), not part of the Candidate Issuance/Briefing Record model at all.

---

## 6. Execution Flow

1. Scheduler fires — either the opening-time trigger or a recurring-interval trigger.
2. Orchestrator reads Operational Configuration: active adapters/categories, recipients, and which trigger this is.
3. Orchestrator invokes each active adapter independently; one adapter's failure is isolated and doesn't block the others or the Shared Core.
4. Each adapter Fetches and Validates, emitting `genuine` Candidate Issuance records or an explicit failure signal.
5. Adapter output goes to the Shared Core.
6. Detect compares each candidate's identifier against Issuance State (respecting the baseline exclusion for newly-activated categories).
7. For each new candidate, Assess attempts AI-advisory analysis; failure is caught, the item continues.
8. Compose assembles the Briefing Record, deterministic fields always populated, advisory/best-effort fields populated or explicitly flagged unavailable.
9. Notify applies the branching from §3.7: any new issuance on any check → Regulatory Briefing(s) immediately; opening check with nothing new → Daily Monitoring Report; later check with nothing new → nothing sent.
10. Commit State marks each notified issuance processed only after its own Notify succeeded.
11. Any failure at any step propagates loudly rather than being caught and swallowed, so the scheduling platform's native failure notification can fire (§3.8) — this is independent of steps 1–10 and happens regardless of their outcome.

---

## 7. Adapter vs. Shared Core Responsibilities

| Responsibility | Owner |
|---|---|
| Knowing how to reach a regulator's official source | Adapter |
| Detecting blocked/CAPTCHA/error/malformed responses | Adapter |
| Parsing regulator-specific content structure | Adapter |
| Extracting a stable per-regulator issuance identifier | Adapter |
| Producing normalized Candidate Issuance records | Adapter |
| Comparing candidates against Issuance State (dedup) | Shared Core |
| AI-advisory assessment against Business Context Configuration | Shared Core |
| Assembling the content-contract Briefing Record | Shared Core |
| Daily Monitoring Report vs. Regulatory Briefing branching | Shared Core (Notify) |
| Recipient routing and delivery | Shared Core |
| Marking issuances processed | Shared Core |
| Document archiving | Shared Core (best-effort) |
| Identifying the opening check vs. a recurring check | Orchestrator |
| Letting failures propagate to the scheduling platform's native alerting | Orchestrator |

A new regulator is added by writing a new adapter that satisfies the Candidate Issuance contract — the Shared Core is never modified to accommodate a new source.

---

## 8. Failure Handling, Recovery, Idempotency, Notification Behavior

**Idempotency:** because Commit State only advances after Notify succeeds, re-running the system — manually, or because of an overlapping/delayed trigger — is always safe. A fully-committed issuance is recognized as already-known and produces no further action. An issuance whose Notify didn't previously succeed is re-detected as still-new and re-attempted, possibly producing a duplicate notification — an accepted trade-off, never a corruption of state. This also covers the edge case of the opening check firing more than once on the same day (e.g., due to scheduling-platform imprecision): a second Daily Monitoring Report would be a harmless duplicate, not a defect.

**Recovery:** because state only advances on confirmed success, recovery from essentially any failure is "run again" — no separate rollback mechanism is needed. The one scenario this doesn't cover is a logic bug in an adapter's normalization or identifier extraction, which needs a code fix, not a recovery mechanism.

**Failure isolation:** an adapter failure affects only that adapter's regulator for that run. A Shared Core failure for one issuance affects only that issuance.

**Notification behavior:** exactly as specified in §3.7 — Daily Monitoring Report only on a nothing-found opening check; Regulatory Briefing per issuance, immediately, on any check that finds something; nothing at all on a later nothing-found check; no operational content in either.

---

## 9. Assumptions, Design Decisions, Trade-offs, Known Limitations

- **Assumption:** each adapter can reliably extract a stable identifier despite differing numbering conventions across regulators (see §13 for what's already known).
- **Assumption:** official source access paths (direct, mirror, or proxy) remain available; if a regulator's channel disappears or fundamentally changes, that's outside this system's control by design (not a general anti-bot circumvention platform).
- **Trade-off:** Architecture 3 over full stage-decoupling — doesn't independently solve high-volume scaling or multi-operator concurrency; an explicitly deferred future trigger, not solved now.
- **Trade-off:** fail-open-and-flag on AI/best-effort fields means recipients sometimes receive visibly incomplete briefings — deliberately accepted over any risk of silent loss or indefinite delay.
- **Trade-off:** the Daily Monitoring Report's health signal is point-in-time only — a flaky source that happens to succeed at the moment of the opening check is not flagged that day. Deliberately accepted; revisit only if real operational experience shows it matters.
- **Known limitation:** operational issues (adapter failures, degraded sources) never appear in business-facing notifications by design — this is a deliberate boundary (principle 12), not a gap, but it does mean business recipients have no visibility into source health at all, even during a genuine, sustained outage of one source.
- **Known limitation:** scheduling-platform timing (e.g., GitHub Actions cron) is not minute-precise; "immediately" and "10:00 AM" are both bounded by whatever the actual scheduling platform delivers, which may be tens of minutes later under normal operation.
- **Known, accepted residual gap:** nothing in this design detects the scheduling trigger failing to fire at all (as distinct from firing and failing) — there's no run, so there's no failure to surface. Closing this fully would require dedicated external monitoring infrastructure, which isn't currently justified (principles 4 and 6).
- **Assumption:** Business Context Configuration will be genuinely maintained by the business; AI assessment quality is bounded by the quality of this input.

---

## 10. Recommended Implementation Roadmap

**Phase 0 — Foundational scaffolding.** Finalize the concrete formats for Candidate Issuance and Briefing Record (§5); stand up concrete storage for the four authoritative records (§3.5); decide the concrete scheduling platform, with the timing caveat in §3.3/§9 in mind.

**Phase 1 — Shared Core, deterministic path only.** Implement Detect, Compose (advisory/best-effort fields stubbed as "unavailable"), the Notify branching logic from §3.7 (including the baseline exclusion and the opening-vs-recurring-check distinction), and Commit State. Test end-to-end with synthetic Candidate Issuance records — no real adapters yet. This proves idempotency and the notification branching independent of any scraping complexity. **[Complete as of this consolidation — see `tests/test_phase1_core.py`.]**

**Phase 2 — First regulator adapter (recommend BIR).** BIR is the most established and directly-accessible source. Implement its Fetch, Validate, and normalization; wire it into the Phase 1 core; validate the full flow end-to-end for one real regulator, including a real Daily Monitoring Report on a quiet day and a real Regulatory Briefing on a day with a new issuance. **[Complete as of this consolidation.]**

**Phase 3 — Remaining adapters (IC, then SEC).** Each fully encapsulates its own access-path handling (§13) without touching the Shared Core. **[Complete as of this consolidation; parsing logic for IC especially should be re-verified against a live, browser-connected inspection — see §13.]**

**Phase 4 — Assess integration.** Implement the AI-advisory step reading Business Context Configuration, wired into the already-validated Compose degradation behavior from Phase 1. **[Not started — intentionally out of scope for this consolidation pass.]**

**Phase 5 — Archive integration.** Best-effort document archiving and link population, using the same fail-open-and-flag handling as any other best-effort field. **[Not started — intentionally out of scope for this consolidation pass.]**

**Phase 6 — Operational hardening.** Implement the baseline mechanism for newly-activated categories (§3.6, §13); confirm the infrastructure-level fail-loud mechanism (§3.8) actually reaches the maintainer, not just a log file; tune the recurring polling interval against actual proxy usage (§3.3). **[Baseline mechanism complete; fail-loud propagation from `main.py` complete; proxy-budget tuning still needs real production data.]**

**Phase 7 — Cutover and monitoring.** Run in parallel with (or in place of) the prior system across at least one full business week before treating this system as the system of record. **[Not started.]**

---

## 11. Suggested Project Structure

```
/adapters/
    bir/        — Fetch, Validate, normalization for BIR
    ic/         — Fetch (via proxy), Validate, normalization for IC
    sec/        — Fetch (via mirror), Validate, normalization for SEC
/core/
    detect/
    assess/
    compose/
    notify/       — includes the Daily Monitoring Report / Regulatory Briefing branching
    commit_state/
/models/        — shared Candidate Issuance and Briefing Record definitions
/config/        — Operational Configuration and Business Context Configuration access
/state/         — Issuance State read/write logic
/orchestration/ — scheduler entry point; identifies opening vs. recurring check; sequences adapters -> core; lets failures propagate
/docs/          — this document, the Architecture Foundation, and adapter-specific notes discovered during implementation
```

**As actually implemented** (see the consolidation summary for the full rationale): `core/adapters/`, `core/` (Shared Core + state + http client + sheets config + notification channel), `models/` (data model), root `main.py` (orchestrator/entry point), `docs/` — the same shape, organized slightly differently for a Python package layout.

---

## 12. Open Implementation Decisions (Deferred — Not Architectural)

- Concrete storage technology/format for the four authoritative records. **[Resolved for now: flat JSON files (`state/seen_issuances.json`) for Issuance State; Google Sheets, via gspread/service-account, for Operational and Business Context Configuration.]**
- Concrete scheduling platform/trigger mechanism — with the documented GitHub Actions timing caveat (§3.3) in mind; if tighter precision is needed later, an external scheduler calling the workflow's dispatch API directly, rather than relying on native cron, is the documented approach. **[Resolved for now: GitHub Actions, as before.]**
- The concrete recurring polling interval — the default of every 30 minutes must be checked against actual free-tier proxy usage for IC once implemented; a coarser interval for IC specifically (versus BIR/SEC) is an acceptable way to stay within budget without changing the architecture. **[Still open — needs real production data; IC currently has no proxy wired in at all (see consolidation summary), so this is moot until that's added.]**
- Concrete AI provider/model for Assess. **[Still open — Phase 4, not started.]**
- Concrete notification delivery mechanism (email provider, etc.). **[Resolved: SMTP/Gmail, via `core/notify_channels.EmailNotificationChannel`.]**
- Concrete archive storage destination and link format. **[Still open — Phase 5, not started.]**
- Concrete per-adapter identifier-extraction and parsing logic. **[Resolved for a first pass — see §13's note on IC needing re-verification against a live page.]**
- The exact mechanism for identifying "the opening check." **[Resolved: matched GitHub Actions cron-schedule identity (`github.event.schedule`), not wall-clock comparison.]**

## 13. Regulator-Specific Adapter Notes (Carried Forward From the Prior System)

This knowledge already exists from the prior system's operation and should be reused, not rediscovered.

**BIR:** Directly accessible — no proxy or mirror needed. Numbering convention observed as "number-year" / "number s.year" style. Recommended as the first adapter to build (Phase 2) since it has no access-path complexity.

**IC (insurance.gov.ph):** Known categories: `IC-ADVISORY`, `IC-CL`, `IC-MC` — narrower than an initial pass that also tried Legal Opinions and IC Ruling before being scoped down. IC's nav label "Memorandum Circulars" does not match its actual URL slug (`/category/memoranda/`) or issuance prefix (`IMC`) — confirmed by direct inspection, not assumed; parsing/identifier logic should not rely on the nav label. `IC-ADVISORY` mixes two sub-series on one page: "MSS-" (office/administrative notices) and "RS-" (actual regulatory advisories) — may need filtering to RS-only if MSS noise becomes a problem. IC blocks requests from datacenter/cloud IP ranges (confirmed via live 403s from GitHub Actions' IPs specifically) — a scraping proxy is required. A proven cost-control pattern: stop paginating a category once a page returns only already-known items, which keeps proxy usage to roughly one request per category per run — worth preserving to stay within a typical ~1,000 requests/month free tier. Numbering convention observed as "year-number" (e.g., "Circular Letter No. 2025-22").

**Note from this consolidation pass:** the rebuilt `core/adapters/ic_adapter.py` fetches directly (no proxy) against `insurance.gov.ph/category/circular-letters/`, using WordPress `<article>`-based parsing. It does not yet re-add the ScraperAPI-style proxy previously found necessary against GitHub Actions' IP ranges, since no proxy credential/config existed anywhere in the pre-consolidation codebase to carry forward. **If IC starts returning 403s from GitHub Actions in production, that's this exact previously-solved problem recurring — reintroduce a proxy, don't re-diagnose from scratch.**

**SEC:** The main site (www.sec.gov.ph) blocks non-browser requests entirely, including from server-side fetch tools. The working access path is the mirror subdomain `appointment.sec.gov.ph`, which serves the same content and responds normally. Known categories: `SEC-MC`, `SEC-OPINION`, `SEC-DECISION`, `SEC-RESOLUTION`. Numbering convention differs by category: circulars use a number/year style similar to BIR's, but Decisions and Resolutions use a docket-number format — adapter identifier logic must not assume one format applies across all of SEC's categories. **This consolidation's rebuilt SEC adapter now correctly targets the mirror subdomain — this was the single most severe defect found in the pre-consolidation implementation (both prior adapter trees targeted the blocked main site).**

**General parsing note:** because exact HTML structure for IC and SEC was never visually confirmed via a connected browser in the prior system's build, parsing was done generically — regex-matching visible link text against known issuance-number formats rather than depending on specific CSS classes. A fresh, browser-connected inspection of each site's current structure before or during implementation would likely improve robustness and is worth doing rather than assuming the prior generic approach is optimal. **This still applies post-consolidation — the rebuilt IC/SEC adapters are also generic/regex-based, not verified against a live browser session.**

**Baseline mechanism (correctness-critical, not optional):** the first time any category is scraped — whether at initial launch or when a new category is later activated — whatever is found must be recorded as already-known in Issuance State without triggering any Regulatory Briefing. Without this, activating a category with years of backlog would flood recipients with old issuances treated as new, and could exhaust AI/email rate limits in the process — this exact failure happened once in the prior system. This baseline exclusion is what Detect's "new" definition already accounts for in §3.6; it is not a separate mechanism to bolt on later. **Implemented and verified as of this consolidation — see the consolidation summary.**

---

## 14. Final Consistency Review (Original Design-Phase Review)

Performed as a consolidation pass across the entire design process, checking the Foundation, this document's own sections, and the notification strategy for agreement.

**Category 1 — corrected as part of this consolidation (each was a genuine contradiction with the now-final notification strategy, not a new architectural idea):**
- The Critical Path and component descriptions previously described the Daily Status notification as a separate, parallel mechanism from the main pipeline, and described a distinct "Heartbeat/Evidence" component. Both were corrected: there is one execution flow: the Daily Monitoring Report is simply one possible output of Notify on the opening check, not a separate subsystem, and no dedicated heartbeat component exists.
- Notify was previously described as producing "one digest per regulator per run." This directly contradicted the later-approved immediate, per-issuance Regulatory Briefing requirement and has been corrected throughout.
- Principle 9 and the Failure Philosophy previously stated that evidence of execution must be produced "independent of the notification path." Under the final design, business-facing evidence *is* delivered through the notification path (the Daily Monitoring Report / Regulatory Briefing pair). This is resolved by distinguishing two signals explicitly (§3.8): that pair proves business-facing engagement, while genuine independent failure detection is provided by the existing infrastructure-level fail-loud mechanism, which must remain in place. This mechanism was proposed twice during the design process and never withdrawn — retaining it resolves the contradiction using only previously-approved elements, not a new one.

**Category 2 — implementation guidance (not architectural, included in §12 and §13):**
- The default 30-minute recurring interval must be checked against IC's actual proxy usage once implemented; a differentiated interval per adapter is an acceptable, non-architectural way to stay in budget.
- Identifying "the opening check" should rely on which schedule trigger fired, not on wall-clock proximity, given scheduling-platform timing imprecision. **[Implemented.]**
- A fresh, browser-connected inspection of IC's and SEC's current page structure is recommended before finalizing adapter parsing logic. **[Still outstanding.]**

**Category 3 — future enhancements, intentionally deferred, not part of this architecture:**
- Historical/trend-based source-health tracking, if operational experience later shows the point-in-time signal is insufficient.
- Detecting the scheduling trigger failing to fire at all (as opposed to firing and failing) — would require new external monitoring infrastructure not currently justified.
- Full stage-decoupling (the rejected Architecture 2 shape), if volume, regulator count, or operator count grow enough to justify it.
- Tighter-than-cron-precision scheduling (an external scheduler calling the workflow's dispatch API), if "promptly" ever needs to mean something closer to real time.

**The architecture was frozen and implementation has since been consolidated against it — see `Regulatory-Scraper-Implementation-Review.md` for the audit that preceded consolidation and the consolidation summary for what was actually built.**
