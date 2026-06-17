"""email_service 단위 테스트 — SMTP 전송 없이 함수 로직 검증."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ── _send_html_email 래퍼 테스트 ─────────────────────────────

@pytest.mark.asyncio
async def test_send_html_email_calls_aiosmtplib(monkeypatch):
    """_send_html_email이 aiosmtplib.send를 정상 호출한다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_port", 587)
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")
    monkeypatch.setattr("app.config.settings.smtp_password", "password")
    monkeypatch.setattr("app.config.settings.smtp_from", "noreply@test.com")

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        from app.services.email_service import _send_html_email

        await _send_html_email("user@example.com", "테스트 제목", "<p>본문</p>")
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["hostname"] == "smtp.test.com"
        assert call_kwargs["port"] == 587


# ── send_exchange_rate_alert ────────────────────────────────

@pytest.mark.asyncio
async def test_send_exchange_rate_alert_smtp_not_configured(monkeypatch):
    """SMTP 미설정 시 이메일을 발송하지 않는다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "")
    monkeypatch.setattr("app.config.settings.smtp_user", "")

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        from app.services.email_service import send_exchange_rate_alert

        await send_exchange_rate_alert(
            to_email="user@example.com",
            target_rate=1300.0,
            direction="BELOW",
            current_rate=1295.5,
        )
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_send_exchange_rate_alert_success(monkeypatch):
    """SMTP 설정 시 이메일 제목에 목표 환율이 포함된다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_port", 587)
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")
    monkeypatch.setattr("app.config.settings.smtp_password", "password")
    monkeypatch.setattr("app.config.settings.smtp_from", "noreply@test.com")

    captured_msg = {}

    async def fake_send(msg, **kwargs):
        captured_msg["subject"] = msg["Subject"]

    with patch("aiosmtplib.send", side_effect=fake_send):
        from importlib import reload

        import app.services.email_service as em
        reload(em)

        await em.send_exchange_rate_alert(
            to_email="user@example.com",
            target_rate=1300.0,
            direction="BELOW",
            current_rate=1295.5,
        )

    assert "1,300" in captured_msg.get("subject", "")
    assert "이하" in captured_msg.get("subject", "")


@pytest.mark.asyncio
async def test_send_exchange_rate_alert_above_direction(monkeypatch):
    """direction=ABOVE이면 제목에 '이상'이 포함된다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_port", 587)
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")
    monkeypatch.setattr("app.config.settings.smtp_password", "password")
    monkeypatch.setattr("app.config.settings.smtp_from", "noreply@test.com")

    captured = {}

    async def fake_send(msg, **kwargs):
        captured["subject"] = msg["Subject"]

    with patch("aiosmtplib.send", side_effect=fake_send):
        from importlib import reload

        import app.services.email_service as em
        reload(em)

        await em.send_exchange_rate_alert(
            to_email="user@example.com",
            target_rate=1400.0,
            direction="ABOVE",
            current_rate=1405.0,
        )

    assert "이상" in captured.get("subject", "")


# ── send_stock_price_alert ──────────────────────────────────

@pytest.mark.asyncio
async def test_send_stock_price_alert_smtp_not_configured(monkeypatch):
    """SMTP 미설정 시 주가 알림 이메일을 발송하지 않는다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "")
    monkeypatch.setattr("app.config.settings.smtp_user", "")

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        from app.services.email_service import send_stock_price_alert

        await send_stock_price_alert(
            to_email="user@example.com",
            ticker="005930",
            name="삼성전자",
            target_price=80000.0,
            current_price=79500.0,
            direction="BELOW",
        )
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_send_stock_price_alert_includes_ticker(monkeypatch):
    """주가 알림 이메일 제목에 종목명과 티커가 포함된다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_port", 587)
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")
    monkeypatch.setattr("app.config.settings.smtp_password", "password")
    monkeypatch.setattr("app.config.settings.smtp_from", "noreply@test.com")

    captured = {}

    async def fake_send(msg, **kwargs):
        captured["subject"] = msg["Subject"]

    with patch("aiosmtplib.send", side_effect=fake_send):
        from importlib import reload

        import app.services.email_service as em
        reload(em)

        await em.send_stock_price_alert(
            to_email="user@example.com",
            ticker="005930",
            name="삼성전자",
            target_price=80000.0,
            current_price=79500.0,
            direction="BELOW",
        )

    assert "005930" in captured.get("subject", "")
    assert "삼성전자" in captured.get("subject", "")


# ── send_monthly_report_email ───────────────────────────────

@pytest.mark.asyncio
async def test_send_monthly_report_email_smtp_not_configured(monkeypatch):
    """SMTP 미설정 시 월간 리포트 이메일을 발송하지 않는다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "")
    monkeypatch.setattr("app.config.settings.smtp_user", "")

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        from app.services.email_service import send_monthly_report_email

        await send_monthly_report_email(
            to_email="user@example.com",
            report_month="2026년 5월",
            total_assets_krw=100_000_000.0,
            mom_change_krw=5_000_000.0,
            mom_change_pct=5.0,
            annual_return_pct=12.0,
            xirr_pct=11.5,
            goal_amount=1_000_000_000.0,
            goal_achievement_pct=10.0,
            annual_deposit_goal=24_000_000.0,
            deposit_achievement_pct=50.0,
            annual_dividends_received=2_000_000.0,
            asset_allocation=[],
        )
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_send_monthly_report_email_includes_month(monkeypatch):
    """월간 리포트 이메일 제목에 월이 포함된다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_port", 587)
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")
    monkeypatch.setattr("app.config.settings.smtp_password", "password")
    monkeypatch.setattr("app.config.settings.smtp_from", "noreply@test.com")

    captured = {}

    async def fake_send(msg, **kwargs):
        captured["subject"] = msg["Subject"]
        captured["body"] = msg.get_payload(decode=False)

    with patch("aiosmtplib.send", side_effect=fake_send):
        from importlib import reload

        import app.services.email_service as em
        reload(em)

        await em.send_monthly_report_email(
            to_email="user@example.com",
            report_month="2026년 5월",
            total_assets_krw=100_000_000.0,
            mom_change_krw=None,
            mom_change_pct=None,
            annual_return_pct=None,
            xirr_pct=None,
            goal_amount=None,
            goal_achievement_pct=None,
            annual_deposit_goal=None,
            deposit_achievement_pct=None,
            annual_dividends_received=2_000_000.0,
            asset_allocation=[],
        )

    assert "2026년 5월" in captured.get("subject", "")


@pytest.mark.asyncio
async def test_send_monthly_report_email_asset_allocation_sorted(monkeypatch):
    """자산 배분이 금액 내림차순으로 정렬되어 상위 5개만 포함된다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_port", 587)
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")
    monkeypatch.setattr("app.config.settings.smtp_password", "password")
    monkeypatch.setattr("app.config.settings.smtp_from", "noreply@test.com")

    # 6개 항목 — 상위 5개만 이메일에 포함되어야 함
    asset_allocation = [
        {"type": "BANK_ACCOUNT", "amount_krw": 10_000_000, "pct": 10},
        {"type": "STOCK_KIS", "amount_krw": 50_000_000, "pct": 50},
        {"type": "DEPOSIT", "amount_krw": 5_000_000, "pct": 5},
        {"type": "REAL_ESTATE", "amount_krw": 20_000_000, "pct": 20},
        {"type": "CASH_OTHER", "amount_krw": 3_000_000, "pct": 3},
        {"type": "OTHER", "amount_krw": 2_000_000, "pct": 2},  # 6번째 — 제외되어야 함
    ]

    html_captured = []

    async def fake_send(msg, **kwargs):
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                html_captured.append(part.get_payload(decode=True).decode("utf-8"))

    with patch("aiosmtplib.send", side_effect=fake_send):
        from importlib import reload

        import app.services.email_service as em
        reload(em)

        await em.send_monthly_report_email(
            to_email="user@example.com",
            report_month="2026년 5월",
            total_assets_krw=90_000_000.0,
            mom_change_krw=None,
            mom_change_pct=None,
            annual_return_pct=None,
            xirr_pct=None,
            goal_amount=None,
            goal_achievement_pct=None,
            annual_deposit_goal=None,
            deposit_achievement_pct=None,
            annual_dividends_received=0.0,
            asset_allocation=asset_allocation,
        )

    if html_captured:
        html = html_captured[0]
        # 상위 5개 (STOCK_KIS, REAL_ESTATE, BANK_ACCOUNT, DEPOSIT, CASH_OTHER)는 포함
        assert "주식(KIS)" in html
        # 6번째 항목 "OTHER"은 5위 안에 들지 않아야 함 (OTHER은 2백만원으로 가장 작음)
        # CASH_OTHER(3백만)은 포함, OTHER(2백만)은 제외
        assert "기타" not in html.split("현금(기타)")[1] if "현금(기타)" in html else True


# ── send_goal_achievement_email ─────────────────────────────

@pytest.mark.asyncio
async def test_send_goal_achievement_email_asset_type(monkeypatch):
    """총 자산 목표 달성 이메일 제목에 달성률이 포함된다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_port", 587)
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")
    monkeypatch.setattr("app.config.settings.smtp_password", "password")
    monkeypatch.setattr("app.config.settings.smtp_from", "noreply@test.com")

    captured = {}

    async def fake_send(msg, **kwargs):
        captured["subject"] = msg["Subject"]

    with patch("aiosmtplib.send", side_effect=fake_send):
        from importlib import reload

        import app.services.email_service as em
        reload(em)

        await em.send_goal_achievement_email(
            to_email="user@example.com",
            goal_type="ASSET",
            goal_amount=1_000_000_000.0,
            current_amount=1_050_000_000.0,
            achievement_pct=105.0,
        )

    assert "105.0%" in captured.get("subject", "")


@pytest.mark.asyncio
async def test_send_goal_achievement_email_deposit_type(monkeypatch):
    """연간 입금 목표 달성 이메일 제목에 '연간 입금 목표'가 포함된다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_port", 587)
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")
    monkeypatch.setattr("app.config.settings.smtp_password", "password")
    monkeypatch.setattr("app.config.settings.smtp_from", "noreply@test.com")

    captured = {}

    async def fake_send(msg, **kwargs):
        captured["subject"] = msg["Subject"]

    with patch("aiosmtplib.send", side_effect=fake_send):
        from importlib import reload

        import app.services.email_service as em
        reload(em)

        await em.send_goal_achievement_email(
            to_email="user@example.com",
            goal_type="DEPOSIT",
            goal_amount=24_000_000.0,
            current_amount=25_000_000.0,
            achievement_pct=104.2,
        )

    assert "연간 입금 목표" in captured.get("subject", "")


# ── send_test_email ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_test_email_raises_when_no_smtp(monkeypatch):
    """SMTP 미설정 시 send_test_email은 RuntimeError를 발생시킨다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "")
    monkeypatch.setattr("app.config.settings.smtp_user", "")

    from app.services.email_service import send_test_email

    with pytest.raises(RuntimeError, match="smtp_not_configured"):
        await send_test_email("user@example.com")


@pytest.mark.asyncio
async def test_send_test_email_success(monkeypatch):
    """SMTP 설정 시 테스트 이메일이 발송된다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_port", 587)
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")
    monkeypatch.setattr("app.config.settings.smtp_password", "password")
    monkeypatch.setattr("app.config.settings.smtp_from", "noreply@test.com")

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        from importlib import reload

        import app.services.email_service as em
        reload(em)

        await em.send_test_email("user@example.com")
        mock_send.assert_called_once()


# ── send_password_reset_email ───────────────────────────────

@pytest.mark.asyncio
async def test_send_password_reset_email_smtp_not_configured(monkeypatch):
    """SMTP 미설정 시 비밀번호 재설정 이메일을 발송하지 않는다 (경고 로그만)."""
    monkeypatch.setattr("app.config.settings.smtp_host", "")
    monkeypatch.setattr("app.config.settings.smtp_user", "")

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        from app.services.email_service import send_password_reset_email

        await send_password_reset_email("user@example.com", "https://reset-link/token")
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_send_password_reset_email_includes_link(monkeypatch):
    """비밀번호 재설정 이메일 본문에 reset 링크가 포함된다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_port", 587)
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")
    monkeypatch.setattr("app.config.settings.smtp_password", "password")
    monkeypatch.setattr("app.config.settings.smtp_from", "noreply@test.com")

    html_captured = []

    async def fake_send(msg, **kwargs):
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                html_captured.append(part.get_payload(decode=True).decode("utf-8"))

    with patch("aiosmtplib.send", side_effect=fake_send):
        from importlib import reload

        import app.services.email_service as em
        reload(em)

        await em.send_password_reset_email(
            "user@example.com", "https://growlio.app/reset-password?token=abc123"
        )

    if html_captured:
        assert "abc123" in html_captured[0]


# ── send_rebalancing_alert ──────────────────────────────────

@pytest.mark.asyncio
async def test_send_rebalancing_alert_smtp_not_configured(monkeypatch):
    """SMTP 미설정 시 리밸런싱 알림 이메일을 발송하지 않는다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "")
    monkeypatch.setattr("app.config.settings.smtp_user", "")

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        from app.services.email_service import send_rebalancing_alert

        await send_rebalancing_alert(
            to_email="user@example.com",
            portfolio_name="성장 포트폴리오",
            threshold_pct=5.0,
            items_to_show=[],
            drifting_count=0,
        )
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_send_rebalancing_alert_scheduled_report(monkeypatch):
    """is_scheduled_report=True이면 제목에 '리포트'가 포함된다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_port", 587)
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")
    monkeypatch.setattr("app.config.settings.smtp_password", "password")
    monkeypatch.setattr("app.config.settings.smtp_from", "noreply@test.com")

    from types import SimpleNamespace

    item = SimpleNamespace(
        name="삼성전자",
        ticker="005930",
        target_weight_pct=50.0,
        current_weight_pct=55.0,
        weight_diff_pct=-5.0,
        diff_krw=-500_000,
        shares_to_trade=10,
        market="KOSPI",
    )

    captured = {}

    async def fake_send(msg, **kwargs):
        captured["subject"] = msg["Subject"]

    with patch("aiosmtplib.send", side_effect=fake_send):
        from importlib import reload

        import app.services.email_service as em
        reload(em)

        await em.send_rebalancing_alert(
            to_email="user@example.com",
            portfolio_name="성장 포트폴리오",
            threshold_pct=5.0,
            items_to_show=[item],
            drifting_count=1,
            is_scheduled_report=True,
            schedule_type="MONTHLY",
        )

    assert "리포트" in captured.get("subject", "")
    assert "성장 포트폴리오" in captured.get("subject", "")


@pytest.mark.asyncio
async def test_send_rebalancing_alert_drift_branch(monkeypatch):
    """is_scheduled_report=False이면 제목에 '알림'이 포함된다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_port", 587)
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")
    monkeypatch.setattr("app.config.settings.smtp_password", "password")
    monkeypatch.setattr("app.config.settings.smtp_from", "noreply@test.com")

    from types import SimpleNamespace
    item = SimpleNamespace(
        name="삼성전자", ticker="005930",
        target_weight_pct=50.0, current_weight_pct=45.0, weight_diff_pct=5.0,
        diff_krw=500_000, shares_to_trade=10, market="KOSPI",
    )
    captured = {}

    async def fake_send(msg, **kwargs):
        captured["subject"] = msg["Subject"]

    with patch("aiosmtplib.send", side_effect=fake_send):
        from importlib import reload

        import app.services.email_service as em
        reload(em)

        await em.send_rebalancing_alert(
            to_email="user@example.com",
            portfolio_name="성장 포트폴리오",
            threshold_pct=5.0,
            items_to_show=[item],
            drifting_count=1,
            is_scheduled_report=False,
        )

    assert "알림" in captured.get("subject", "")


@pytest.mark.asyncio
async def test_send_monthly_report_with_all_values(monkeypatch):
    """월간 리포트에 MoM/수익률/목표 값이 모두 채워지면 해당 행이 생성된다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_port", 587)
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")
    monkeypatch.setattr("app.config.settings.smtp_password", "password")
    monkeypatch.setattr("app.config.settings.smtp_from", "noreply@test.com")

    html_captured = []

    async def fake_send(msg, **kwargs):
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                html_captured.append(part.get_payload(decode=True).decode("utf-8"))

    with patch("aiosmtplib.send", side_effect=fake_send):
        from importlib import reload

        import app.services.email_service as em
        reload(em)

        await em.send_monthly_report_email(
            to_email="user@example.com",
            report_month="2026년 5월",
            total_assets_krw=100_000_000.0,
            mom_change_krw=5_000_000.0,
            mom_change_pct=5.0,
            annual_return_pct=12.5,
            xirr_pct=11.0,
            goal_amount=1_000_000_000.0,
            goal_achievement_pct=10.0,
            annual_deposit_goal=24_000_000.0,
            deposit_achievement_pct=50.0,
            annual_dividends_received=2_000_000.0,
            asset_allocation=[],
        )

    assert len(html_captured) > 0
    html = html_captured[0]
    assert "전월 대비" in html
    assert "연환산 수익률" in html


# ── Exception handlers ────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_exchange_rate_alert_exception_raised(monkeypatch):
    """_send_html_email 예외 시 re-raise."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")

    from unittest.mock import AsyncMock

    import app.services.email_service as em

    with (
        patch.object(em, "_send_html_email", new=AsyncMock(side_effect=Exception("smtp error"))),
        pytest.raises(Exception, match="smtp error"),
    ):
        await em.send_exchange_rate_alert(
            to_email="user@example.com",
            target_rate=1300.0,
            direction="BELOW",
            current_rate=1295.0,
        )


@pytest.mark.asyncio
async def test_send_rebalancing_alert_exception_raised(monkeypatch):
    """_send_html_email 예외 시 re-raise."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")

    from unittest.mock import AsyncMock

    import app.services.email_service as em

    with (
        patch.object(em, "_send_html_email", new=AsyncMock(side_effect=Exception("smtp error"))),
        pytest.raises(Exception, match="smtp error"),
    ):
        await em.send_rebalancing_alert(
            to_email="user@example.com",
            portfolio_name="포트폴리오",
            threshold_pct=5.0,
            items_to_show=[],
            drifting_count=0,
        )


@pytest.mark.asyncio
async def test_send_monthly_report_exception_raised(monkeypatch):
    """월간 리포트 이메일 발송 실패 시 re-raise."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")

    from unittest.mock import AsyncMock

    import app.services.email_service as em

    with (
        patch.object(em, "_send_html_email", new=AsyncMock(side_effect=Exception("smtp error"))),
        pytest.raises(Exception, match="smtp error"),
    ):
        await em.send_monthly_report_email(
            to_email="user@example.com",
            report_month="2026년 5월",
            total_assets_krw=100_000_000.0,
            mom_change_krw=None, mom_change_pct=None,
            annual_return_pct=None, xirr_pct=None,
            goal_amount=None, goal_achievement_pct=None,
            annual_deposit_goal=None, deposit_achievement_pct=None,
            annual_dividends_received=0.0,
            asset_allocation=[],
        )


@pytest.mark.asyncio
async def test_send_stock_price_alert_exception_raised(monkeypatch):
    """send_stock_price_alert _send_html_email 예외 시 re-raise."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")

    from unittest.mock import AsyncMock

    import app.services.email_service as em

    with (
        patch.object(em, "_send_html_email", new=AsyncMock(side_effect=Exception("smtp error"))),
        pytest.raises(Exception, match="smtp error"),
    ):
        await em.send_stock_price_alert(
            to_email="user@example.com",
            ticker="005930",
            name="삼성전자",
            target_price=80000.0,
            current_price=79500.0,
            direction="BELOW",
        )


@pytest.mark.asyncio
async def test_send_goal_achievement_exception_raised(monkeypatch):
    """send_goal_achievement_email 예외 시 re-raise."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")

    from unittest.mock import AsyncMock

    import app.services.email_service as em

    with (
        patch.object(em, "_send_html_email", new=AsyncMock(side_effect=Exception("smtp error"))),
        pytest.raises(Exception, match="smtp error"),
    ):
        await em.send_goal_achievement_email(
            to_email="user@example.com",
            goal_type="ASSET",
            goal_amount=1_000_000_000.0,
            current_amount=1_050_000_000.0,
            achievement_pct=105.0,
        )


@pytest.mark.asyncio
async def test_send_test_email_exception_raised(monkeypatch):
    """send_test_email 예외 시 re-raise."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")

    from unittest.mock import AsyncMock

    import app.services.email_service as em

    with (
        patch.object(em, "_send_html_email", new=AsyncMock(side_effect=Exception("smtp error"))),
        pytest.raises(Exception, match="smtp error"),
    ):
        await em.send_test_email("user@example.com")


@pytest.mark.asyncio
async def test_send_password_reset_exception_silenced(monkeypatch):
    """send_password_reset_email은 예외 발생 시 re-raise 없이 조용히 실패한다."""
    monkeypatch.setattr("app.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("app.config.settings.smtp_user", "test@test.com")

    from unittest.mock import AsyncMock

    import app.services.email_service as em

    with patch.object(em, "_send_html_email", new=AsyncMock(side_effect=Exception("smtp error"))):
        # 예외가 propagate되지 않아야 함
        await em.send_password_reset_email(
            "user@example.com", "https://growlio.app/reset?token=abc"
        )
