import os
from unittest import mock

from core.config import Settings, settings


def test_default_settings():
    """Verify default setting values when environment variables are unset."""
    with mock.patch.dict(os.environ, {}, clear=True):
        config = Settings()
        assert config.STATE_FILE_PATH == "state/seen_issuances.json"
        assert config.SLACK_WEBHOOK_URL is None


def test_custom_environment_settings():
    """Verify that settings correctly load values overridden by environment variables."""
    env_vars = {
        "STATE_FILE_PATH": "custom/path/issuances.json",
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/test/webhook",
    }
    with mock.patch.dict(os.environ, env_vars):
        config = Settings()
        assert config.STATE_FILE_PATH == "custom/path/issuances.json"
        assert config.SLACK_WEBHOOK_URL == "https://hooks.slack.com/services/test/webhook"


def test_global_settings_instance():
    """Verify that the exported global settings instance is valid."""
    assert hasattr(settings, "STATE_FILE_PATH")
    assert hasattr(settings, "SLACK_WEBHOOK_URL")
