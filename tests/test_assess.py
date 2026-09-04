import json
from unittest.mock import MagicMock, patch

from core.assess import Assessor, AssessmentResult, DEFAULT_BUSINESS_CONTEXT
from models.issuance import CandidateIssuance


def _candidate():
    return CandidateIssuance(
        source_regulator="BIR",
        source_category="RMC",
        issuance_identifier="RMC No. 61-2026",
        issuance_title="RMC No. 61-2026 - Test circular",
        source_url="https://www.bir.gov.ph/test",
        raw_content_reference="raw",
    )


def test_assess_fails_open_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assessor = Assessor()

    result = assessor.assess(_candidate())

    assert isinstance(result, AssessmentResult)
    assert result.succeeded is False
    assert result.executive_summary == "UNAVAILABLE"
    assert "ANTHROPIC_API_KEY" in result.error


def test_assess_fails_open_on_api_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assessor = Assessor()
    assessor._client = MagicMock()
    assessor._client.messages.create.side_effect = RuntimeError("boom")

    result = assessor.assess(_candidate())

    assert result.succeeded is False
    # Was `== "boom"`. Errors now carry their exception type (and cause chain,
    # see test below) because a bare message was undiagnosable in production.
    assert result.error == "RuntimeError: boom"
    assert result.risk_priority_level == "UNAVAILABLE"


def test_assess_error_reports_underlying_cause_not_just_wrapper(monkeypatch):
    """Anthropic's APIConnectionError says only "Connection error."; the real
    reason lives in __cause__. Losing it cost a diagnostic round-trip on
    2026-09-04, so the cause chain must survive into the reported error."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assessor = Assessor()
    assessor._client = MagicMock()

    try:
        raise ConnectionRefusedError("[Errno 111] Connection refused")
    except ConnectionRefusedError as cause:
        wrapper = RuntimeError("Connection error.")
        wrapper.__cause__ = cause
        assessor._client.messages.create.side_effect = wrapper

    result = assessor.assess(_candidate())

    assert result.succeeded is False
    assert "Connection error." in result.error
    assert "Connection refused" in result.error, "the actionable detail was dropped"


def test_client_is_configured_with_a_workable_connect_timeout(monkeypatch):
    """The SDK default is a 5s connect timeout, which every assessment in the
    2026-09-04 GitHub Actions run failed against."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = Assessor()._get_client()

    assert client.timeout.connect >= 15
    assert client.max_retries >= 3


def test_assess_parses_successful_response(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assessor = Assessor()

    fake_block = MagicMock()
    fake_block.text = json.dumps({
        "executive_summary": "Summary text.",
        "insurance_entity_impact": "Affects MIGI reserving.",
        "brokerage_entity_impact": "No material impact identified.",
        "risk_priority_level": "Medium",
        "suggested_action": "Review reserving policy.",
    })
    fake_response = MagicMock()
    fake_response.content = [fake_block]

    assessor._client = MagicMock()
    assessor._client.messages.create.return_value = fake_response

    result = assessor.assess(_candidate())

    assert result.succeeded is True
    assert result.executive_summary == "Summary text."
    assert result.risk_priority_level == "Medium"


def test_assess_strips_markdown_fences_if_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assessor = Assessor()

    fake_block = MagicMock()
    fake_block.text = "```json\n" + json.dumps({
        "executive_summary": "Fenced summary.",
        "insurance_entity_impact": "No material impact identified.",
        "brokerage_entity_impact": "No material impact identified.",
        "risk_priority_level": "Low",
        "suggested_action": "No action required.",
    }) + "\n```"
    fake_response = MagicMock()
    fake_response.content = [fake_block]

    assessor._client = MagicMock()
    assessor._client.messages.create.return_value = fake_response

    result = assessor.assess(_candidate())

    assert result.succeeded is True
    assert result.executive_summary == "Fenced summary."


def test_business_context_falls_back_to_default_when_sheet_empty():
    config_reader = MagicMock()
    config_reader.get_business_context.return_value = []
    assessor = Assessor(config_reader=config_reader)

    text = assessor._business_context_text()

    assert "MIGI" in text
    assert DEFAULT_BUSINESS_CONTEXT[0]["Field"] in text


def test_business_context_uses_sheet_when_present():
    config_reader = MagicMock()
    config_reader.get_business_context.return_value = [
        {"Field": "Custom Focus", "Checklist text": "Watch for microinsurance rules."}
    ]
    assessor = Assessor(config_reader=config_reader)

    text = assessor._business_context_text()

    assert "Custom Focus" in text
    assert "microinsurance" in text
