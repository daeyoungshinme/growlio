"""app/core/logging.py의 시크릿 redaction 프로세서 테스트."""

import logging
from unittest.mock import patch

import structlog

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

    def test_redacts_kis_account_number_in_url(self):
        """httpx 오류 문자열의 요청 URL에 실린 계좌번호를 가린다 (plans/156 A4)."""
        text = (
            "Client error '400 Bad Request' for url "
            "'https://openapi.koreainvestment.com:9443/uapi/overseas-stock/v1/trading/inquire-balance"
            "?CANO=12345678&ACNT_PRDT_CD=01&OVRS_EXCG_CD=NASD'"
        )
        redacted = redact_secrets(text)
        assert "12345678" not in redacted
        assert "CANO=[REDACTED]" in redacted
        assert "OVRS_EXCG_CD=NASD" in redacted


class TestFormatSyncError:
    def test_unmapped_exception_hides_raw_text(self):
        """매핑 안 된 예외(SQLAlchemy·httpx)의 원문은 last_sync_error로 나가지 않는다 (plans/156 A5)."""
        from app.core.logging import format_sync_error

        err = KeyError("SELECT * FROM users WHERE token = 'abc'")
        assert format_sync_error(err) == "내부 오류가 발생했습니다(KeyError)"

    def test_our_messages_pass_through(self):
        from app.core.logging import format_sync_error
        from app.exceptions import ProviderApiError
        from app.utils.circuit_breaker import CircuitOpenError

        assert format_sync_error(ProviderApiError("토스 계좌 조회 실패")) == "토스 계좌 조회 실패"
        assert format_sync_error(CircuitOpenError("KIS API 일시 차단")) == "KIS API 일시 차단"

    def test_string_is_redacted_and_truncated(self):
        from app.core.logging import SYNC_ERROR_MESSAGE_MAX_LENGTH, format_sync_error

        out = format_sync_error("appkey=PSxxxxxxxx " + "가" * 500)
        assert "PSxxxxxxxx" not in out
        assert len(out) == SYNC_ERROR_MESSAGE_MAX_LENGTH


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
        mock_configure.assert_called_once_with(
            processors=["a", "b", structlog.processors.format_exc_info, _redact_processor, "renderer"]
        )

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

    def test_drops_quote_not_found_404_noise(self):
        f = _DropBenignYFinance404()
        msg = (
            'HTTP Error 404: {"quoteSummary":{"result":null,"error":'
            '{"code":"Not Found","description":"Quote not found for symbol: 039560.KS"}}}'
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
