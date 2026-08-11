import os
from unittest import mock

from core.config import Settings, settings


def test_default_settings():
    """Verify default setting values when environment variables are unset."""
    with mock.patch.dict(os.environ, {}, clear=True):
        config = Settings()
        assert config.STATE_FILE_PATH == "state/seen_issuances.json"


def test_custom_environment_settings():
    """Verify that settings correctly load values overridden by environment variables."""
    env_vars = {
        "STATE_FILE_PATH": "custom/path/issuances.json",
    }
    with mock.patch.dict(os.environ, env_vars):
        config = Settings()
        assert config.STATE_FILE_PATH == "custom/path/issuances.json"


def test_global_settings_instance():
    """Verify that the exported global settings instance is valid."""
    assert hasattr(settings, "STATE_FILE_PATH")
