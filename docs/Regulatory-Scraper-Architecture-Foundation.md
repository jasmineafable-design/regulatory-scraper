# Regulatory Scraper — Architecture Foundation

**Status: FROZEN.** This document is the authoritative statement of what this system must do and why. It must not be silently reinterpreted or redesigned. Any perceived conflict between this foundation and an implementation choice must be surfaced explicitly for the project owner's decision, not resolved unilaterally.

**Approved architecture:** Architecture 3 — Federated Source Adapters with a Shared Core (see the Implementation Handoff document for full architectural detail). This foundation defines what any implementation of that architecture must satisfy.

---

## 1. System Goals

**Primary (measurable):**

1. **Reliability** — every new issuance published through BIR's, IC's, and SEC's official sources must be detected and its notification delivered promptly, with no silent failure. "Promptly" is defined concretely by the Notification Strategy (§7): each new issuance is reported immediately upon detection, on whichever monitoring cycle finds it, rather than held for a batch or waiting for the next day's opening check.
2. **Actionability** — every Regulatory Briefing notification must let a process owner understand an issuance's relevance and required action in under a minute, without opening the source document, by satisfying the minimum content contract (§2).

**Secondary:** the system must remain operable by a single part-time maintainer, and must remain adaptable to business change through configuration alone, without code changes.

## 2. Functional Requirements

**Minimum content contract** — every Regulatory Briefing notification must contain:
- Issuance number/title
- Executive summary
- Insurance entity impact (MIGI/MILI)
- Brokerage entity impact (MIBI)
- Risk/priority level
- Suggested action
- Link to the archived copy of the document
- Link to the official regulator source

Any field above that cannot be produced (an AI-derived field, or a best-effort field like the archive link) must be explicitly flagged as unavailable in the notification — never silently omitted, and the notification must never be presented as complete when it isn't.

**Configurability** — the following must be editable by non-technical users, without any code change:
- Business context: company profile, current strategic initiatives, products and services, business activities, regulatory focus areas, topics currently important to the company, and specific things the AI should evaluate.
- Recipients, routed per regulator/category.
- Notification schedule parameters: the business-day calendar (default Monday–Friday), the daily opening-check time (default 10:00 AM), and the recurring polling interval used for the rest of the day (default every 30 minutes).

**Notification types** — see §7 for the full specification. In summary: a **Daily Monitoring Report** (business-facing, sent only when the day's opening check finds nothing new) and a **Regulatory Briefing** (business-facing, sent immediately per issuance whenever anything new is detected, on any check that day). Operational/maintainer diagnostics are explicitly excluded from both — see §7 and §8.

## 3. Constraints

- One part-time maintainer; no dedicated ops/SRE support.
- Real incidents already occurred and define the actual risk surface, not hypothetical risk: an unrelated domain migration silently broke Gmail-based email sending; a bug once mis-recorded a failed fetch as "genuinely nothing new," which nearly caused a backlog flood when a category was first activated; IC blocks requests from datacenter/cloud IP ranges; SEC's main site blocks non-browser traffic and is instead reached via a mirror subdomain (`appointment.sec.gov.ph`).
- Must operate within free-tier budgets throughout (scheduling, any scraping proxy, any AI provider). This directly bears on the recurring polling interval (§7): a shorter interval means more fetches, and any adapter requiring a paid-tier-adjacent proxy (currently IC) must have its effective check frequency chosen with that budget in mind — this is implementation guidance, not a fixed number (see the Handoff document §12).
- GitHub Actions' own scheduled-workflow timing is not guaranteed to the minute; documented delays of 5–30 minutes are normal, and 30–60+ minute delays are possible under load. "Promptly" in §1 is bounded by whatever scheduling platform is actually chosen, not by an assumption of exact timing.
- The prior system already runs on Google Workspace (Sheets, Drive, Gmail) and GitHub-based tooling — existing environment, not a mandated future stack, but a real starting point worth reusing rather than discarding.
- Each regulator site has distinct, previously-unknown-until-encountered access restrictions. This is an ongoing discovery problem, not something solvable once and forgotten.
- No dedicated monitoring/alerting infrastructure exists or should be built new for this system.

## 4. Design Principles

1. **Detection over prevention**, where prevention isn't achievable — the system's job is to notice when access to a source breaks, not guarantee it never will.
2. **Fail loud, never silent** — a failure that's caught and logged but never surfaced to a human is architecturally indistinguishable from one that isn't caught at all.
3. **Isolate failure domains** — one source, or one non-critical step, failing must not take down the others.
4. **Reuse existing infrastructure before building new infrastructure.**
5. **Configuration changes deserve the same traceability as code changes.**
6. **Complexity is proportional to actual, not anticipated, scale.**
7. **Duplicate notifications are acceptable; silent data loss is not.**
8. **All scheduled runs must be idempotent** — re-running a completed job, in full or from any intermediate point, must never create inconsistent state, even if it produces a duplicate notification.
9. **Positive evidence that the system is operating is required once per business day**, produced by the outcome of that day's opening check — either the Daily Monitoring Report (if nothing was found) or the Regulatory Briefing itself (if something was found). Both are equally valid proof that the system engaged with real content that day. This is distinct from, and does not replace, genuine failure detection (§8, Failure Philosophy) — a business-facing content signal and an infrastructure-level execution-failure signal serve different purposes and must not be conflated.
10. **AI is advisory only.** It may summarize, assess impact, classify, and recommend action. It never determines whether an issuance exists, whether it is reported, or whether notification occurs — those three decisions are deterministic, derived solely from validated source data and application logic, never from model output.
11. **Business-context configuration, recipients, and notification schedule parameters must all be externally editable by non-technical users** — as the business changes, the configuration changes, not the application.
12. **Business-facing notifications and operational/maintainer diagnostics are distinct concerns and must not be merged.** Adapter failures, degraded sources, and notification-channel failures are surfaced exclusively through existing fail-loud infrastructure behavior and logs — addressed to the maintainer — never through Daily Monitoring Report or Regulatory Briefing content. This is a deliberate, revisitable-only-with-real-evidence boundary, not an oversight.

**Approved decision on AI/best-effort failure (frozen):** if AI assessment fails, or any other best-effort field (such as the archive link) cannot be produced, the system must still deliver the Regulatory Briefing using all available deterministic information, with the missing sections explicitly identified. The system must never silently omit required analysis or present an incomplete briefing as complete.

## 5. Source of Truth

Four authoritative records exist. How each is stored is an implementation decision, not a property of what's authoritative:

- **Issuance State** — the record of which issuances are already known/processed.
- **Operational Configuration** — which sources/categories are active, who is notified for each, and the notification schedule parameters (business days, opening time, polling interval).
- **Business Context Configuration** — company profile, strategic initiatives, products/services, business activities, regulatory focus areas, current topics of interest, custom evaluation criteria.
- **Application Logic** — the code that fetches, validates, detects, assesses, composes, and notifies.

No fifth record (such as a persistent failure-history or "health" store) is currently justified. This was deliberately considered and rejected: source health, as used in the Daily Monitoring Report, refers only to the outcome of that day's opening check — a point-in-time result, not a trend — and requires no retained history to produce. If future operational experience demonstrates a real need for historical degradation tracking, that can be introduced later; it is not part of the current architecture.

**Only content originating from an official regulator publication channel is authoritative.** Where direct access is technically blocked, an access path (a mirror or a proxy) may be used to reach that same official content, but the access path itself is never an independent source of truth — if it ever diverges from the regulator's actual publication, the regulator's publication governs.

Any dashboard, log, or archive is always a rendering of one of the four records above — never a fifth, independent store of the same fact.

## 6. Critical Path

There is exactly one execution flow, invoked repeatedly on a single recurring schedule (an opening check at a configured daily time, then recurring checks at a configured interval for the rest of the business day):

**Fetch → Validate → Detect → Assess → Compose → Notify → Commit State**

- **Fetch** — retrieve a response from, or through a sanctioned access path to, an official regulator source.
- **Validate** — confirm the response is genuine content, not a CAPTCHA challenge, a block page, an error response, or malformed/empty content. A response that fails validation is a failure — never reinterpreted as "no new issuances."
- **Detect** — deterministically compare validated content against Issuance State to identify what's new. A category being baselined for the first time (see §7) is excluded from "new" here by definition, not treated as a large batch of new issuances.
- **Assess** — AI-advisory step: summarize, classify impact, recommend action, bounded by Business Context Configuration. May fail without halting the item.
- **Compose** — assemble the notification's required content-contract fields; explicitly flag any field that could not be produced.
- **Notify** — deliver the composed output. On any check, if one or more new issuances were found, this means one Regulatory Briefing per issuance, sent immediately. On the opening check of the business day specifically, if nothing new was found, this means the Daily Monitoring Report instead. On any later check that finds nothing, Notify produces nothing at all — this is expected and not itself a failure signal.
- **Commit State** — mark an issuance as processed only after Notify has succeeded for it.

This ordering is deliberate: state only advances once delivery is confirmed, so a failure at any point up to and including Notify can never cause an issuance to be silently lost — the next check will detect it as still-new and try again.

## 7. Notification Strategy

There are exactly two business-facing notification types, and they are mutually exclusive outcomes of the same underlying check, not two separate subsystems:

**Daily Monitoring Report** — sent only when the opening check of the business day (default: weekdays, default 10:00 AM, both configurable) finds zero new issuances. States this explicitly (e.g., "no new relevant issuances were found as of 10:00 AM"), and sets the expectation that monitoring continues through the day and that any newly detected issuance will generate its own immediate notification. Contains no operational diagnostics and no per-source health detail — it is a business-perspective statement about content, not a system-status report.

**Regulatory Briefing** — sent immediately, per issuance, whenever any check that day (the opening one or any later one) detects something new. Contains the full minimum content contract (§2). If the opening check finds one or more new issuances, the corresponding Briefing(s) are sent and no Daily Monitoring Report is sent that day — the two are mutually exclusive outputs of that specific check.

**Every check after the opening one:** finds something new → Regulatory Briefing, immediately. Finds nothing → no notification at all. This is expected behavior, not a gap — silence on a "nothing new" check is normal.

**What this deliberately excludes:** there is no separate heartbeat notification, no per-cycle status message, and no persistent record of source health across cycles. A source that fails validation on the opening check is reported that day only insofar as it affects whether anything new was found — it is never named or diagnosed in either business-facing notification. Operational issues are a maintainer concern (§8), not a business-facing one, by deliberate design.

**Accepted trade-off:** because the opening check's source-health signal is a single point-in-time result, a source that is genuinely flaky — failing most checks but happening to succeed at the moment of the opening check — will not be flagged as degraded that day. This is a known, deliberately accepted limitation, not an oversight, and is the direct consequence of choosing not to retain failure history (§5).

## 8. Failure Philosophy

- Fail closed on state, fail open on delivery: never mark an issuance processed without a confirmed notification; never withhold a validated, detected item because a downstream enrichment step failed.
- Prefer a duplicate notification over any risk of silent loss — safe specifically because runs are idempotent (§4, principle 8).
- Correlated failures should read as one legible story, not many unrelated-looking alarms.
- **Two distinct signals serve two distinct purposes and must not be collapsed into one.** The Daily Monitoring Report / Regulatory Briefing pair provides the business with proof that the system engaged with real content once per day (principle 9) — but because both are delivered through the same notification channel, their absence is not, by itself, an independent proof of failure: if the notification channel itself is what's broken, both would be silent for the same reason. The genuinely independent signal — one whose failure mode differs from the notification channel's — is the existing infrastructure-level fail-loud mechanism (e.g., letting an execution error fail the scheduled job itself, so the scheduling platform's own native failure notification fires). That mechanism must remain in place underneath the notification strategy in §7; it is not replaced by it.
- Operational issues (adapter failures, degraded sources, notification-channel failures) are surfaced through that same infrastructure-level mechanism and through logs — a maintainer concern, never merged into business-facing content (principle 12).
- Silent *data* loss and silent *quality* loss are both failures: an issuance that's never reported, and a briefing that's sent looking complete but is actually missing required analysis, are the same category of problem.
- **Known, accepted residual gap:** none of the above detects the case where the scheduling trigger never fires at all (as opposed to firing and failing) — there is no run, so there is nothing to fail loudly and nothing to be silent about. This is an accepted limitation, consistent with principles 4 and 6 (reuse existing infrastructure, proportional complexity) — closing it fully would require dedicated new monitoring infrastructure that isn't currently justified.

## 9. Non-Goals

- Not a substitute for professional or legal judgment — the system surfaces issuances and advisory commentary; a qualified person decides actual applicability.
- Not an automatic legal-applicability determination system.
- Not a full document management system — archiving exists so a source document can be located later, not to provide records-management or retention guarantees.
- Not a real-time alerting system — detection runs on a scheduled cadence, not instant publish-to-notify latency.
- Not a general anti-bot circumvention platform — the system detects and surfaces when access to a source breaks; it does not guarantee it can always defeat blocking measures.
- Not an operational monitoring or observability platform for business recipients — operational health and diagnostics are intentionally excluded from business-facing notifications; this is a deliberate boundary, revisitable only if real operational experience demonstrates a genuine need.
- Not a historical or trend-based source-health tracker — the opening check's health signal is point-in-time only, by design (see the accepted trade-off in §7).
- AI-generated summaries and impact assessments are not guaranteed exhaustive or error-free, and their usefulness is bounded by the quality of the Business Context Configuration supplied. Thin or stale configuration will produce generic output — an expected limitation of the mechanism, not a defect to engineer away.

---

*This foundation, together with the approved Architecture 3, is frozen. See the Implementation Handoff document for full component detail, execution flow, data model, roadmap, and the final consistency review.*
