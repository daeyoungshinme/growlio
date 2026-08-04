"""app/core/logging.py의 시크릿 redaction 프로세서 테스트."""

from unittest.mock import patch

from app.core.logging import _redact_processor, configure_logging, redact_secrets


class TestRedactSecrets:
    def test_redacts_appkey_value(self):
        assert redact_secrets("appkey=PSxxxxxxxxxxxxxxxxxx") == "appkey=[REDACTED]"

    def test_redacts_access_token_in_sentence(self):
        text = 'token issue failed: access_token: "abcdEFGH1234" was rejected'
        redacted = redact_secrets(text)
        assert "abcdEFGH1234" not in redacted
        assert "access_token=[REDACTED]" in redacted

    def test_leaves_non_secret_text_untouched(self):
        text = "account_synced positions=3"
        assert redact_secrets(text) == text


class TestRedactProcessor:
    def test_redacts_string_values_in_event_dict(self):
        event_dict = {"event": "kis_token_issue_failed", "error": "appkey=SECRET1234VALUE"}
        result = _redact_processor(None, "error", event_dict)
        assert result["error"] == "appkey=[REDACTED]"

    def test_leaves_non_string_values_untouched(self):
        event_dict = {"event": "account_synced", "positions": 3}
        result = _redact_processor(None, "info", event_dict)
        assert result["positions"] == 3


class TestConfigureLogging:
    def test_noop_when_already_configured(self):
        with (
            patch("app.core.logging.structlog.is_configured", return_value=True),
            patch("app.core.logging.structlog.configure") as mock_configure,
        ):
            configure_logging()
        mock_configure.assert_not_called()

    def test_inserts_redact_processor_before_last_when_not_configured(self):
        fake_processors = ["a", "b", "renderer"]
        with (
            patch("app.core.logging.structlog.is_configured", return_value=False),
            patch("app.core.logging.structlog.get_config", return_value={"processors": fake_processors}),
            patch("app.core.logging.structlog.configure") as mock_configure,
        ):
            configure_logging()
        mock_configure.assert_called_once_with(processors=["a", "b", _redact_processor, "renderer"])
