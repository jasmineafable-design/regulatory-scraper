# File: tests/test_notifier.py

import pytest
from unittest.mock import patch, MagicMock
from src.notifier.email_notifier import EmailNotifier


def test_email_notifier_empty_items():
    notifier = EmailNotifier()
    # Sending no items should return True without attempting to send email
    assert notifier.send_alert([]) is True


@patch.dict("os.environ", {}, clear=True)
def test_email_notifier_missing_credentials_fails_loud():
    notifier = EmailNotifier()
    sample_items = [{"title": "SEC MC 1", "url": "http://sec.gov.ph/1", "regulator": "SEC"}]
    
    # Expect ValueError when SMTP parameters are missing
    with pytest.raises(ValueError, match="EmailNotifier configuration missing"):
        notifier.send_alert(sample_items)


@patch.dict("os.environ", {
    "SMTP_SERVER": "smtp.example.com",
    "SMTP_PORT": "587",
    "SMTP_SENDER_EMAIL": "bot@example.com",
    "SMTP_SENDER_PASSWORD": "secretpassword",
    "NOTIFICATION_RECIPIENTS": "alert1@example.com, alert2@example.com"
})
@patch("smtplib.SMTP")
def test_email_notifier_success(mock_smtp):
    mock_server_instance = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_server_instance

    notifier = EmailNotifier()
    sample_items = [{"title": "SEC MC 10-2026", "url": "http://sec.gov.ph/mc10", "regulator": "SEC"}]

    result = notifier.send_alert(sample_items)

    assert result is True
    mock_server_instance.starttls.assert_called_once()
    mock_server_instance.login.assert_called_once_with("bot@example.com", "secretpassword")
    mock_server_instance.sendmail.assert_called_once()
