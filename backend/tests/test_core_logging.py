"""app/core/logging.py의 시크릿 redaction 프로세서 테스트."""

import logging
from unittest.mock import patch

from app.core.logging import (
    _DropBenignYFinance404,
    _redact_processor,
    configure_logging,
    redact_secrets,
)


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

    def test_attaches_yfinance_noise_filter_once(self):
        yf_logger = logging.getLogger("yfinance")
        yf_logger.filters = [f for f in yf_logger.filters if not isinstance(f, _DropBenignYFinance404)]
        try:
            with patch("app.core.logging.structlog.is_configured", return_value=True):
                configure_logging()
                configure_logging()
            attached = [f for f in yf_logger.filters if isinstance(f, _DropBenignYFinance404)]
            assert len(attached) == 1
        finally:
            yf_logger.filters = [f for f in yf_logger.filters if not isinstance(f, _DropBenignYFinance404)]


class TestDropBenignYFinance404:
    def _record(self, msg: str) -> logging.LogRecord:
        return logging.LogRecord("yfinance", logging.ERROR, __file__, 0, msg, None, None)

    def test_drops_quotesummary_404_noise(self):
        f = _DropBenignYFinance404()
        msg = (
            'HTTP Error 404: {"quoteSummary":{"result":null,"error":'
            '{"code":"Not Found","description":"No fundamentals data found for symbol: SPYG"}}}'
        )
        assert f.filter(self._record(msg)) is False

    def test_passes_through_other_yfinance_logs(self):
        f = _DropBenignYFinance404()
        assert f.filter(self._record("YFRateLimitError: Too Many Requests. Rate limited.")) is True
        assert f.filter(self._record("network unreachable")) is True

    def test_passes_through_non_quotesummary_404(self):
        """상장폐지 티커의 가격 조회(`.history()`) 404 등은 삼키지 않는다."""
        f = _DropBenignYFinance404()
        assert f.filter(self._record("DELISTED?: possibly delisted; no price data found  (1d)")) is True
        assert f.filter(self._record("HTTP Error 404: Not Found for url https://.../v8/finance/chart/XYZ")) is True
