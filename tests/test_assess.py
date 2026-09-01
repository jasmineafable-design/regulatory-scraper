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
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assessor = Assessor()

    result = assessor.assess(_candidate())

    assert isinstance(result, AssessmentResult)
    assert result.succeeded is False
    assert result.executive_summary == "UNAVAILABLE"
    assert "OPENAI_API_KEY" in result.error


def test_assess_fails_open_on_api_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assessor = Assessor()
    assessor._client = MagicMock()
    assessor._client.chat.completions.create.side_effect = RuntimeError("boom")

    result = assessor.assess(_candidate())

    assert result.succeeded is False
    assert result.error == "boom"
    assert result.risk_priority_level == "UNAVAILABLE"


def test_assess_parses_successful_response(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assessor = Assessor()

    fake_message = MagicMock()
    fake_message.content = json.dumps({
        "executive_summary": "Summary text.",
        "insurance_entity_impact": "Affects MIGI reserving.",
        "brokerage_entity_impact": "No material impact identified.",
        "risk_priority_level": "Medium",
        "suggested_action": "Review reserving policy.",
    })
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=fake_message)]

    assessor._client = MagicMock()
    assessor._client.chat.completions.create.return_value = fake_response

    result = assessor.assess(_candidate())

    assert result.succeeded is True
    assert result.executive_summary == "Summary text."
    assert result.risk_priority_level == "Medium"


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
