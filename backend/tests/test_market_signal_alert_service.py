"""market_signal_alert_service.py 단위 테스트 — 시장 신호 등급 변화 감지·알림."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.market_signal_service import get_last_composite_level, set_last_composite_level
from app.services.rebalancing.diagnosis_service import _MARKET_NOTES


class TestLastLevelRoundTrip:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_row(self, mock_db):
        mock_db.get = AsyncMock(return_value=None)
        assert await get_last_composite_level(mock_db) is None

    @pytest.mark.asyncio
    async def test_set_then_get_round_trip(self, mock_db):
        await set_last_composite_level(mock_db, "YELLOW")
        mock_db.execute.assert_called_once()

        from app.models.app_state import AppState

        mock_db.get = AsyncMock(return_value=AppState(key="last_level", value="YELLOW", expires_at=None))
        result = await get_last_composite_level(mock_db)
        assert result == "YELLOW"


class TestGetCompositeSubscribers:
    @pytest.mark.asyncio
    async def test_query_does_not_join_rebalancing_alert(self, mock_db):
        """활성 RebalancingAlert 보유 여부와 무관하게 구독 대상을 조회해야 한다(계획15 B4/11).

        수동 리밸런싱만 쓰거나 알림을 하나도 설정하지 않은 유저도 이 토글만으로
        구독되어야 하므로, 생성되는 쿼리 자체가 rebalancing_alerts 테이블을 참조하면 안 된다.
        """
        from app.services.alerts.market_signal_alert_service import _get_composite_subscribers

        await _get_composite_subscribers(mock_db)

        mock_db.execute.assert_called_once()
        statement = mock_db.execute.call_args[0][0]
        compiled_sql = str(statement.compile(compile_kwargs={"literal_binds": True})).lower()
        assert "rebalancing_alerts" not in compiled_sql

    @pytest.mark.asyncio
    async def test_includes_user_without_any_rebalancing_alert(self, mock_db):
        """리밸런싱 알림이 0개인 유저도 composite_signal_alerts_enabled만 True면 대상에 포함된다."""
        from app.services.alerts.market_signal_alert_service import _get_composite_subscribers

        user = SimpleNamespace(id=uuid.uuid4(), email="no-alerts@example.com", is_active=True)
        user_settings = SimpleNamespace(composite_signal_alerts_enabled=True)

        execute_result = MagicMock()
        execute_result.all.return_value = [(user, user_settings)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        subscribers = await _get_composite_subscribers(mock_db)

        assert subscribers == [(user, user_settings)]


class TestCheckMarketSignalLevelChange:
    @pytest.mark.asyncio
    async def test_first_run_stores_without_notifying(self, mock_db, mock_cache):
        """이전 관측값이 없으면(최초 실행) 저장만 하고 알림을 보내지 않는다."""
        from app.services.alerts.market_signal_alert_service import check_market_signal_level_change

        mock_db.get = AsyncMock(return_value=None)
        with (
            patch(
                "app.services.alerts.market_signal_alert_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch("app.services.email_service.send_market_signal_change_alert", new=AsyncMock()) as mock_email,
        ):
            await check_market_signal_level_change(mock_db, mock_cache)

        mock_email.assert_not_called()
        # last_level 저장은 durable_state(db) 경유 — set_durable이 내부적으로 커밋한다.
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_change_does_nothing(self, mock_db, mock_cache):
        """이전 관측값과 동일하면 아무 것도 하지 않는다."""
        from app.models.app_state import AppState
        from app.services.alerts.market_signal_alert_service import check_market_signal_level_change

        mock_db.get = AsyncMock(return_value=AppState(key="last_level", value="GREEN", expires_at=None))
        with (
            patch(
                "app.services.alerts.market_signal_alert_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch("app.services.email_service.send_market_signal_change_alert", new=AsyncMock()) as mock_email,
        ):
            await check_market_signal_level_change(mock_db, mock_cache)

        mock_email.assert_not_called()
        mock_db.execute.assert_not_called()
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_level_change_notifies_subscribers_and_saves_history(self, mock_db, mock_cache):
        """등급이 바뀌면 composite_signal_alerts_enabled=True인 구독자에게 이메일+푸시 발송, 이력 저장, 커밋."""
        from app.models.app_state import AppState
        from app.services.alerts.market_signal_alert_service import check_market_signal_level_change

        user = SimpleNamespace(id=uuid.uuid4(), email="user@example.com", is_active=True)
        user_settings = SimpleNamespace(notification_email=None, fcm_token="token-abc")

        execute_result = MagicMock()
        execute_result.all.return_value = [(user, user_settings)]
        mock_db.execute = AsyncMock(return_value=execute_result)
        mock_db.get = AsyncMock(return_value=AppState(key="last_level", value="GREEN", expires_at=None))

        with (
            patch(
                "app.services.alerts.market_signal_alert_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "RED"}),
            ),
            patch(
                "app.services.email_service.send_market_signal_change_alert",
                new=AsyncMock(return_value=True),
            ) as mock_email,
            patch(
                "app.services.push_service.send_push_to_user",
                new=AsyncMock(return_value=True),
            ) as mock_push,
        ):
            await check_market_signal_level_change(mock_db, mock_cache)

        mock_email.assert_called_once()
        args, kwargs = mock_email.call_args
        assert args[0] == "user@example.com"
        assert args[1] == "GREEN"
        assert args[2] == "RED"

        mock_push.assert_called_once()
        # db.execute 3회: (1) 구독자 쿼리 (2) 복합신호 dedup 플래그 저장(durable) (3) last_level 저장(durable)
        # rebalancing_alert_service와 dedup 키를 공유해 같은 날 두 서비스가 중복 발송하지 않도록 함
        assert mock_db.execute.call_count == 3
        # commit 3회: dedup 저장(set_durable) + save_alert_history 이력 저장 후 + last_level 저장(set_durable)
        assert mock_db.commit.call_count == 3

    @pytest.mark.asyncio
    async def test_no_subscribers_still_updates_last_level(self, mock_db, mock_cache):
        """구독자가 없어도 마지막 관측값은 갱신된다."""
        from app.models.app_state import AppState

        execute_result = MagicMock()
        execute_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)
        mock_db.get = AsyncMock(return_value=AppState(key="last_level", value="GREEN", expires_at=None))

        from app.services.alerts.market_signal_alert_service import check_market_signal_level_change

        with patch(
            "app.services.alerts.market_signal_alert_service.get_market_signal",
            new=AsyncMock(return_value={"composite_level": "RED"}),
        ):
            await check_market_signal_level_change(mock_db, mock_cache)

        # 알림 발송 경로(email/push/save_alert_history)는 타지 않았으므로 그 경로의 commit은 없다.
        # last_level 저장(set_durable)만 내부적으로 1회 커밋한다.
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_market_signal_fetch_failure_is_swallowed(self, mock_db, mock_cache):
        """시장 신호 조회 실패 시 예외를 삼키고 조용히 반환한다."""
        from app.services.alerts.market_signal_alert_service import check_market_signal_level_change

        with patch(
            "app.services.alerts.market_signal_alert_service.get_market_signal",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await check_market_signal_level_change(mock_db, mock_cache)

        mock_db.execute.assert_not_called()
        mock_cache.setex.assert_not_called()


class TestAlreadySentDigestToday:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_history(self, mock_db):
        from app.services.alerts.market_signal_alert_service import _already_sent_digest_today

        result_mock = MagicMock()
        result_mock.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        assert await _already_sent_digest_today(mock_db, uuid.uuid4()) is False

    @pytest.mark.asyncio
    async def test_returns_true_when_history_exists(self, mock_db):
        from app.services.alerts.market_signal_alert_service import _already_sent_digest_today

        result_mock = MagicMock()
        result_mock.scalar.return_value = uuid.uuid4()
        mock_db.execute = AsyncMock(return_value=result_mock)

        assert await _already_sent_digest_today(mock_db, uuid.uuid4()) is True


class TestSendMarketSignalDailyDigest:
    @pytest.mark.asyncio
    async def test_fetch_failure_is_swallowed(self, mock_db, mock_cache):
        """시장 신호 조회 실패 시 예외를 삼키고 구독자 조회조차 하지 않는다."""
        from app.services.alerts.market_signal_alert_service import send_market_signal_daily_digest

        with patch(
            "app.services.alerts.market_signal_alert_service.get_market_signal",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await send_market_signal_daily_digest(mock_db, mock_cache)

        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_subscribers_sends_nothing(self, mock_db, mock_cache):
        from app.services.alerts.market_signal_alert_service import send_market_signal_daily_digest

        execute_result = MagicMock()
        execute_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch(
                "app.services.alerts.market_signal_alert_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch("app.services.email_service.send_market_signal_daily_digest_alert", new=AsyncMock()) as mock_email,
        ):
            await send_market_signal_daily_digest(mock_db, mock_cache)

        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_email_and_push_and_saves_history(self, mock_db, mock_cache):
        """구독 유저에게 이메일+푸시 발송 후 이력 저장 + 커밋."""
        from app.services.alerts.market_signal_alert_service import send_market_signal_daily_digest

        user = SimpleNamespace(id=uuid.uuid4(), email="user@example.com", is_active=True)
        user_settings = SimpleNamespace(notification_email=None, fcm_token="token-abc")

        subscribers_result = MagicMock()
        subscribers_result.all.return_value = [(user, user_settings)]
        mock_db.execute = AsyncMock(return_value=subscribers_result)

        history_result = MagicMock()
        history_result.scalar.return_value = None  # 아직 오늘 발송 안 함

        per_user_session = AsyncMock()
        per_user_session.execute = AsyncMock(return_value=history_result)
        per_user_session.add = MagicMock()
        per_user_session.commit = AsyncMock()
        per_user_session.__aenter__ = AsyncMock(return_value=per_user_session)
        per_user_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "app.services.alerts.market_signal_alert_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "RED"}),
            ),
            patch(
                "app.services.alerts.market_signal_alert_service.AsyncSessionLocal",
                return_value=per_user_session,
            ),
            patch(
                "app.services.email_service.send_market_signal_daily_digest_alert",
                new=AsyncMock(return_value=True),
            ) as mock_email,
            patch(
                "app.services.push_service.send_push_to_user",
                new=AsyncMock(return_value=True),
            ) as mock_push,
        ):
            await send_market_signal_daily_digest(mock_db, mock_cache)

        mock_email.assert_called_once_with("user@example.com", "RED", _MARKET_NOTES["RED"])
        mock_push.assert_called_once()
        push_kwargs = mock_push.call_args.kwargs
        assert push_kwargs["fcm_token"] == "token-abc"
        assert push_kwargs["data"] == {"type": "MARKET_SIGNAL_DIGEST"}
        per_user_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_green_level_uses_fallback_reason(self, mock_db, mock_cache):
        """GREEN은 _MARKET_NOTES에 None이 매핑되어 있으므로 안내 문구로 대체한다(빈 메시지 방지)."""
        from app.services.alerts.market_signal_alert_service import send_market_signal_daily_digest

        user = SimpleNamespace(id=uuid.uuid4(), email="user@example.com", is_active=True)
        user_settings = SimpleNamespace(notification_email=None, fcm_token=None)

        subscribers_result = MagicMock()
        subscribers_result.all.return_value = [(user, user_settings)]
        mock_db.execute = AsyncMock(return_value=subscribers_result)

        history_result = MagicMock()
        history_result.scalar.return_value = None

        per_user_session = AsyncMock()
        per_user_session.execute = AsyncMock(return_value=history_result)
        per_user_session.__aenter__ = AsyncMock(return_value=per_user_session)
        per_user_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "app.services.alerts.market_signal_alert_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch(
                "app.services.alerts.market_signal_alert_service.AsyncSessionLocal",
                return_value=per_user_session,
            ),
            patch(
                "app.services.email_service.send_market_signal_daily_digest_alert",
                new=AsyncMock(return_value=True),
            ) as mock_email,
            patch("app.services.push_service.send_push_to_user", new=AsyncMock(return_value=False)),
        ):
            await send_market_signal_daily_digest(mock_db, mock_cache)

        mock_email.assert_called_once_with("user@example.com", "GREEN", "오늘도 안정적입니다.")

    @pytest.mark.asyncio
    async def test_skips_user_already_notified_today(self, mock_db, mock_cache):
        """오늘 이미 발송된 유저는 건너뛴다 — 스케줄러 재시작/misfire 중복 발송 방지."""
        from app.services.alerts.market_signal_alert_service import send_market_signal_daily_digest

        user = SimpleNamespace(id=uuid.uuid4(), email="user@example.com", is_active=True)
        user_settings = SimpleNamespace(notification_email=None, fcm_token=None)

        subscribers_result = MagicMock()
        subscribers_result.all.return_value = [(user, user_settings)]
        mock_db.execute = AsyncMock(return_value=subscribers_result)

        history_result = MagicMock()
        history_result.scalar.return_value = uuid.uuid4()  # 이미 발송됨

        per_user_session = AsyncMock()
        per_user_session.execute = AsyncMock(return_value=history_result)
        per_user_session.__aenter__ = AsyncMock(return_value=per_user_session)
        per_user_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "app.services.alerts.market_signal_alert_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch(
                "app.services.alerts.market_signal_alert_service.AsyncSessionLocal",
                return_value=per_user_session,
            ),
            patch("app.services.email_service.send_market_signal_daily_digest_alert", new=AsyncMock()) as mock_email,
        ):
            await send_market_signal_daily_digest(mock_db, mock_cache)

        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_one_user_failure_does_not_stop_others(self, mock_db, mock_cache):
        """한 유저 처리 중 예외가 발생해도 다른 유저 처리는 계속된다."""
        from app.services.alerts.market_signal_alert_service import send_market_signal_daily_digest

        user1 = SimpleNamespace(id=uuid.uuid4(), email="u1@example.com", is_active=True)
        user2 = SimpleNamespace(id=uuid.uuid4(), email="u2@example.com", is_active=True)
        settings1 = SimpleNamespace(notification_email=None, fcm_token=None)
        settings2 = SimpleNamespace(notification_email=None, fcm_token=None)

        subscribers_result = MagicMock()
        subscribers_result.all.return_value = [(user1, settings1), (user2, settings2)]
        mock_db.execute = AsyncMock(return_value=subscribers_result)

        def session_factory():
            session = AsyncMock()
            session.__aenter__ = AsyncMock(return_value=session)
            session.__aexit__ = AsyncMock(return_value=None)
            session.execute = AsyncMock(side_effect=RuntimeError("db down"))
            return session

        with (
            patch(
                "app.services.alerts.market_signal_alert_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch(
                "app.services.alerts.market_signal_alert_service.AsyncSessionLocal",
                side_effect=session_factory,
            ),
            patch("app.services.email_service.send_market_signal_daily_digest_alert", new=AsyncMock()) as mock_email,
        ):
            # 두 유저 모두 세션 조회 단계에서 실패하지만 예외가 전체를 막지 않아야 한다.
            await send_market_signal_daily_digest(mock_db, mock_cache)

        mock_email.assert_not_called()
