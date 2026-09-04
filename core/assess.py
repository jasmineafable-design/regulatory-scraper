"""
Assess step (Foundation §3.6, Phase 4).

AI-advisory only (Foundation principle 10): this module may summarize, assess
impact, classify, and recommend action. It never decides whether an issuance
exists, whether it's reported, or whether notification occurs -- those stay
deterministic and happen in Detect/Notify regardless of what happens here.

Approved AI/best-effort failure behavior (frozen, §3.8): if this fails for
any reason (missing API key, network error, malformed response), Compose must
still produce a Briefing Record from deterministic data alone, with the
missing sections explicitly marked -- never silently incomplete, never
withheld. This module enforces that by never raising: fetch_impact_assessment
always returns an AssessmentResult, with .succeeded=False and an .error on
any failure, and lets the caller (Composer) decide what "UNAVAILABLE" means
for its own fields.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import List, Dict, Optional

from models.issuance import CandidateIssuance

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Bootstrap default, used only when the Sheet's BusinessContext tab is empty
# or unreachable (§3.2 requires this to be non-technical-user-editable
# without a code change -- this default exists so the system produces a
# real assessment on day one, not so Jas has to fill in the Sheet before
# anything works). Replace/extend via the Sheet once real priorities are
# known; no code change needed for that.
DEFAULT_BUSINESS_CONTEXT: List[Dict[str, str]] = [
    {
        "Field": "Company Profile",
        "Checklist text": (
            "MIGI (Moneeinsure General Insurance) and MILI (Moneeinsure Life "
            "Insurance) are underwriters; MIBI (Moneeinsure Brokers Inc.) is a "
            "brokerage, not an underwriter."
        ),
    },
    {
        "Field": "MIGI/MILI Impact Criteria",
        "Checklist text": (
            "Flag as impactful if the issuance affects: underwriting rules or "
            "minimum rates, reserving/capital requirements, product approval or "
            "filing requirements, reportorial/deadline obligations, or "
            "policyholder-facing disclosure requirements for non-life or life "
            "insurers."
        ),
    },
    {
        "Field": "MIBI Impact Criteria",
        "Checklist text": (
            "Flag as impactful if the issuance affects: broker/agent licensing "
            "or accreditation, disclosure or fair-dealing obligations owed to "
            "clients, commission/compensation rules, or reportorial obligations "
            "specific to brokerages rather than underwriters."
        ),
    },
    {
        "Field": "Strategic Initiative — Composite License",
        "Checklist text": (
            "MIGI/MILI are exploring a portfolio transfer in connection with a "
            "composite license application (an insurer authorized to write both "
            "life and non-life). Applies across all regulators (BIR, IC, SEC), "
            "not just IC. Flag as High priority anything related to: composite "
            "licensing requirements, portfolio transfer rules/procedures, "
            "capital or minimum paid-up requirements for composite insurers, "
            "restrictions on holding both life and non-life lines under one "
            "entity, or tax/corporate-structuring implications of a portfolio "
            "transfer."
        ),
    },
    {
        "Field": "Opportunity Flagging (Insurtech)",
        "Checklist text": (
            "Beyond compliance risk, actively flag anything that could be a "
            "beneficial opportunity for an insurtech -- e.g. new digital "
            "distribution allowances, regulatory sandboxes, relaxed "
            "e-KYC/e-signature/electronic-filing rules, InsurTech-specific "
            "circulars, or incentives for technology-driven insurers/brokers. "
            "Note these explicitly as \"Opportunity\" in the suggested action, "
            "not just risk."
        ),
    },
    {
        "Field": "Risk/Priority Guidance",
        "Checklist text": (
            "Rate as High if there's a compliance deadline, mandatory action "
            "required, or a significant opportunity identified above; Medium if "
            "relevant but informational or discretionary; Low if no material "
            "bearing on MIGI/MILI/MIBI."
        ),
    },
]

_SYSTEM_PROMPT = """You are a regulatory compliance analyst assisting an insurance group in the Philippines (MIGI, MILI, MIBI). Given one regulatory issuance and business context, produce a concise, actionable assessment.

Respond with ONLY a JSON object (no markdown fences, no commentary) with exactly these keys:
- "executive_summary": 1-3 sentences, plain language, what this issuance actually says/requires.
- "insurance_entity_impact": impact to MIGI/MILI (non-life/life underwriters), or "No material impact identified." if none.
- "brokerage_entity_impact": impact to MIBI (brokerage), or "No material impact identified." if none.
- "risk_priority_level": one of "High", "Medium", "Low".
- "suggested_action": a concrete next step, or "No action required." if none.

Never fabricate specifics (dates, amounts, section numbers) not evidenced by the issuance title/content given to you -- if the title alone is insufficient to say something specific, keep the summary general rather than inventing detail."""


def _describe_exception(err: BaseException, max_depth: int = 4) -> str:
    """Renders an exception together with its underlying cause chain.

    Anthropic's APIConnectionError carries the useless literal message
    "Connection error." -- the actual reason (DNS failure, TLS handshake
    error, connect timeout, connection refused) lives in __cause__, which
    str(err) discards. That cost a whole diagnostic round-trip on 2026-09-04,
    so failures now report the chain: "APIConnectionError: Connection error.
    <- ConnectTimeout: timed out".
    """
    parts = []
    seen = set()
    current: Optional[BaseException] = err
    depth = 0
    while current is not None and depth < max_depth and id(current) not in seen:
        seen.add(id(current))
        text = str(current).strip() or "(no message)"
        parts.append(f"{type(current).__name__}: {text}")
        current = current.__cause__ or current.__context__
        depth += 1
    return " <- ".join(parts)


@dataclass
class AssessmentResult:
    succeeded: bool
    executive_summary: str = "UNAVAILABLE"
    insurance_entity_impact: str = "UNAVAILABLE"
    brokerage_entity_impact: str = "UNAVAILABLE"
    risk_priority_level: str = "UNAVAILABLE"
    suggested_action: str = "UNAVAILABLE"
    error: Optional[str] = None


class Assessor:
    """AI-advisory impact assessment via the Anthropic API (Phase 4).

    Uses Claude Haiku by default -- cheap enough (~$0.0016/call at this
    prompt's size) that a one-time $5 credit grant covers a very long runway
    at this system's volume. Switched from Groq/OpenAI to Anthropic on
    2026-09-03 per Jas's preference for Claude's summary quality.

    Reads Business Context Configuration from the Sheet (§3.2/§3.5) via the
    injected SheetsConfigReader, falling back to DEFAULT_BUSINESS_CONTEXT when
    the Sheet is empty/unreachable -- consistent with the rest of the system's
    fail-open-on-configuration convention.
    """

    def __init__(self, config_reader=None, model: str = DEFAULT_MODEL):
        self.config_reader = config_reader
        self.model = model
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._client = None

    # The SDK's default connect timeout is 5s with 2 retries. On a GitHub
    # Actions runner that proved too tight -- every assessment in the
    # 2026-09-04 run failed with a bare "Connection error." Widening the
    # connect window and allowing more retries costs nothing when the API is
    # reachable (the read timeout, which governs the actual generation, is
    # unchanged) and removes the most likely cause.
    CONNECT_TIMEOUT_SEC = 20.0
    READ_TIMEOUT_SEC = 120.0
    MAX_RETRIES = 4

    def _get_client(self):
        if self._client is None:
            import httpx
            from anthropic import Anthropic  # imported lazily: optional
            # dependency, and keeps import-time failures from blocking the
            # whole pipeline if the package somehow isn't installed.
            self._client = Anthropic(
                api_key=self.api_key,
                max_retries=self.MAX_RETRIES,
                timeout=httpx.Timeout(
                    connect=self.CONNECT_TIMEOUT_SEC,
                    read=self.READ_TIMEOUT_SEC,
                    write=self.READ_TIMEOUT_SEC,
                    pool=self.READ_TIMEOUT_SEC,
                ),
            )
        return self._client

    def _business_context_text(self) -> str:
        rows = []
        if self.config_reader is not None:
            try:
                rows = self.config_reader.get_business_context()
            except Exception as e:
                logger.warning(f"Failed to read Business Context sheet, using default: {e}")
                rows = []
        if not rows:
            rows = DEFAULT_BUSINESS_CONTEXT
        lines = []
        for row in rows:
            field = str(row.get("Field") or "").strip()
            text = str(row.get("Checklist text") or "").strip()
            if field and text:
                lines.append(f"- {field}: {text}")
        return "\n".join(lines) if lines else "(no business context configured)"

    def assess(self, candidate: CandidateIssuance) -> AssessmentResult:
        """Never raises (see module docstring) -- always returns an
        AssessmentResult, succeeded=False with .error set on any failure."""
        if not self.api_key:
            return AssessmentResult(succeeded=False, error="ANTHROPIC_API_KEY not configured.")

        try:
            client = self._get_client()
            business_context = self._business_context_text()
            user_prompt = (
                f"Business context:\n{business_context}\n\n"
                f"Issuance:\n"
                f"Regulator: {candidate.source_regulator}\n"
                f"Category: {candidate.source_category}\n"
                f"Identifier: {candidate.issuance_identifier}\n"
                f"Title: {candidate.issuance_title}"
            )
            response = client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=0.2,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = response.content[0].text.strip()
            # Claude has no dedicated JSON-mode flag (unlike OpenAI's
            # response_format={"type": "json_object"}); the system prompt asks
            # for bare JSON, but strip markdown fences defensively in case a
            # model ever wraps the object in ```json ... ``` anyway.
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            data = json.loads(raw)

            return AssessmentResult(
                succeeded=True,
                executive_summary=str(data.get("executive_summary") or "UNAVAILABLE"),
                insurance_entity_impact=str(data.get("insurance_entity_impact") or "UNAVAILABLE"),
                brokerage_entity_impact=str(data.get("brokerage_entity_impact") or "UNAVAILABLE"),
                risk_priority_level=str(data.get("risk_priority_level") or "UNAVAILABLE"),
                suggested_action=str(data.get("suggested_action") or "UNAVAILABLE"),
            )
        except Exception as e:
            # Fail-open per the frozen AI/best-effort decision (§3.8, Handoff
            # §"Approved AI/best-effort failure decision"): never let an AI
            # failure block or delay the deterministic briefing.
            detail = _describe_exception(e)
            logger.error(f"[{candidate.source_regulator}] AI assessment failed for "
                         f"{candidate.issuance_identifier}: {detail}")
            return AssessmentResult(succeeded=False, error=detail)
