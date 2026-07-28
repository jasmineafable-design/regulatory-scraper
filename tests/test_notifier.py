import requests
from core.models import CandidateIssuance
from core.notifier import NotificationDispatcher


def test_notifier_no_webhook_fallback():
    dispatcher = NotificationDispatcher(webhook_url=None)
    sample_candidate = CandidateIssuance(
        regulator_id="BIR",
        issuance_identifier="BIR-RMC-No-1-2026",
        title="Sample BIR Issuance",
        document_url="https://example.com/doc.pdf",
    )
    assert dispatcher.dispatch([sample_candidate]) is True


def test_notifier_webhook_success(monkeypatch):
    class MockResponse:
        status_code = 200

        def raise_for_status(self):
            pass

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: MockResponse())

    dispatcher = NotificationDispatcher(webhook_url="https://hooks.slack.com/services/test")
    sample_candidate = CandidateIssuance(
        regulator_id="SEC",
        issuance_identifier="SEC-MC-No-1-2026",
        title="Sample SEC Issuance",
        document_url="https://example.com/sec.pdf",
    )
    assert dispatcher.dispatch([sample_candidate]) is True
