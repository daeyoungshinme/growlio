"""계획 110 배치 D — 실패가 "없음"으로 보이거나 알림·잡이 조용히 사라지던 경로."""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.app_state import AppState

_ALERT = "app.services.alerts.market_signal_alert_service"


def _state(value: str | None) -> AppState | None:
    return AppState(key="k", value=value, expires_at=None) if value is not None else None


def _session(state: AppState | None = None) -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(return_value=state)
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    return db


def _outer_db(notified: str | None, attempts: str | None, subscribers: list[tuple]) -> AsyncMock:
    """키별로 다른 값을 돌려주는 바깥 세션."""
    from app.utils.cache_keys import market_signal_change_attempts_key, market_signal_last_notified_level_key

    values = {
        market_signal_last_notified_level_key(): notified,
        market_signal_change_attempts_key(): attempts,
    }
    db = _session()
    db.get = AsyncMock(side_effect=lambda _model, key: _state(values.get(key)))
    result = MagicMock()
    result.all.return_value = subscribers
    db.execute = AsyncMock(return_value=result)
    return db


def _written_keys(db: AsyncMock) -> dict[str, str]:
    """set_durable이 INSERT에 넘긴 key → value."""
    out = {}
    for call in db.execute.await_args_list:
        params = call.args[0].compile().params if call.args else {}
        if "key" in params and "value" in params:
            out[params["key"]] = params["value"]
    return out


def _subscriber(token="tok"):
    return (
        SimpleNamespace(id=uuid.uuid4(), email="u@example.com", is_active=True),
        SimpleNamespace(notification_email=None, fcm_token=token),
    )


async def _check(db, *, level="RED", user_dbs=None, email=True, push=True):
    from app.services.alerts.market_signal_alert_service import check_market_signal_level_change

    with (
        patch(f"{_ALERT}.get_confirmed_composite_level", new=AsyncMock(return_value=(level, "LIVE"))),
        patch(f"{_ALERT}.AsyncSessionLocal", side_effect=user_dbs or [_session()]),
        patch(
            "app.services.notifications.email_service.send_market_signal_change_alert",
            new=AsyncMock(return_value=email),
        ) as send_email,
        patch("app.services.notifications.push_service.send_push_to_user", new=AsyncMock(return_value=push)),
    ):
        await check_market_signal_level_change(db, MagicMock())
    return send_email


class TestLevelChangeNotice:
    """D1 — 확정은 5~10분 주기 잡이 먼저 한다. "마지막으로 알린 등급"과 비교해야 시간당 잡이 변화를 본다."""

    async def test_notifies_even_when_another_job_confirmed_first(self):
        """확정 등급이 이미 RED여도(다른 잡이 갱신) 알린 등급이 GREEN이면 발송한다 — 예전에는 여기서 유실됐다."""
        from app.utils.cache_keys import market_signal_last_notified_level_key

        db = _outer_db("GREEN", None, [_subscriber()])
        send_email = await _check(db)

        send_email.assert_awaited_once()
        assert send_email.await_args.args[1:3] == ("GREEN", "RED")
        assert _written_keys(db)[market_signal_last_notified_level_key()] == "RED"

    async def test_first_run_stores_without_sending(self):
        from app.utils.cache_keys import market_signal_last_notified_level_key

        db = _outer_db(None, None, [_subscriber()])
        send_email = await _check(db)

        send_email.assert_not_awaited()
        assert _written_keys(db)[market_signal_last_notified_level_key()] == "RED"

    async def test_failed_send_keeps_old_level_for_retry(self):
        from app.utils.cache_keys import market_signal_change_attempts_key, market_signal_last_notified_level_key

        db = _outer_db("GREEN", None, [_subscriber()])
        await _check(db, email=False, push=False)

        written = _written_keys(db)
        assert market_signal_last_notified_level_key() not in written
        assert written[market_signal_change_attempts_key()] == "RED:1"

    async def test_gives_up_after_max_attempts(self):
        """수신 채널이 없는 사용자 때문에 끝없이 재시도하지 않는다."""
        from app.utils.cache_keys import market_signal_last_notified_level_key

        db = _outer_db("GREEN", "RED:2", [_subscriber()])
        await _check(db, email=False, push=False)

        assert _written_keys(db)[market_signal_last_notified_level_key()] == "RED"

    async def test_attempts_for_other_level_do_not_count(self):
        from app.utils.cache_keys import market_signal_change_attempts_key

        db = _outer_db("GREEN", "YELLOW:2", [_subscriber()])
        await _check(db, email=False, push=False)

        assert _written_keys(db)[market_signal_change_attempts_key()] == "RED:1"

    async def test_retry_skips_users_who_already_received(self):
        db = _outer_db("GREEN", "RED:1", [_subscriber()])
        send_email = await _check(db, user_dbs=[_session(_state("1"))])
        send_email.assert_not_awaited()

    async def test_connection_released_before_sending(self):
        db = _outer_db("GREEN", None, [_subscriber()])
        await _check(db)
        assert db.commit.await_count >= 1


class TestActionItemsFailure:
    """D2 — 소스 실패가 "할 일 없음"으로 보이지 않는다."""

    def test_item_names_failed_sources(self):
        from app.services.action_items_service import _partial_failure_item

        item = _partial_failure_item(["tax", "dca"])
        assert item.kind == "PARTIAL_FAILURE"
        assert "세금·적립" in item.detail

    async def test_all_sources_failing_is_not_empty(self):
        from app.services import action_items_service as service

        boom = AsyncMock(side_effect=RuntimeError("down"))
        db = AsyncMock()
        with (
            patch.object(service, "_tactical_items", new=boom),
            patch.object(service, "_rebalance_items", new=boom),
            patch.object(service, "_SOURCES", [("tax", boom)]),
            patch.object(service, "report_handled_failure") as report,
        ):
            items = await service.get_action_items(uuid.uuid4(), db)

        assert [i.kind for i in items] == ["PARTIAL_FAILURE"]
        assert report.call_count == 3

    async def test_failure_notice_survives_item_cap(self):
        from app.schemas.action_items import ActionItem
        from app.services import action_items_service as service

        full = [
            ActionItem(id=str(i), kind="CHALLENGE", priority="HIGH", title="t", detail="d", cta_label="c", link="/")
            for i in range(service.MAX_ACTION_ITEMS)
        ]
        with (
            patch.object(service, "_tactical_items", new=AsyncMock(side_effect=RuntimeError("down"))),
            patch.object(service, "_rebalance_items", new=AsyncMock(return_value=full)),
            patch.object(service, "_SOURCES", []),
            patch.object(service, "report_handled_failure"),
        ):
            items = await service.get_action_items(uuid.uuid4(), AsyncMock())

        assert len(items) == service.MAX_ACTION_ITEMS
        assert items[-1].kind == "PARTIAL_FAILURE"


class TestPeriodicCatchup:
    """D5 — 월 단위 dedup이 있는 잡만, 낮 시간에, 해당 기간에만 다시 돈다."""

    @pytest.mark.parametrize(
        ("now", "expected"),
        [
            (datetime(2026, 11, 1, 10, 25), ["run_monthly_report", "run_challenge_monthly_wrap"]),
            (datetime(2026, 11, 3, 21, 25), ["run_monthly_report", "run_challenge_monthly_wrap"]),
            (datetime(2026, 11, 4, 12, 0), []),
            (datetime(2026, 11, 25, 12, 0), ["run_challenge_deposit_reminder"]),
            (datetime(2026, 11, 28, 12, 0), ["run_challenge_deposit_reminder"]),
            (datetime(2026, 11, 29, 12, 0), []),
            (datetime(2026, 11, 1, 9, 30), []),  # 정시 잡과 겹치는 시간
            (datetime(2026, 11, 1, 22, 0), []),  # 밤에는 보내지 않는다
        ],
    )
    def test_due_jobs(self, now, expected):
        from app.jobs.periodic_catchup import _due_jobs

        assert [job.__name__ for job in _due_jobs(now)] == expected

    async def test_runs_due_jobs(self):
        from app.jobs import periodic_catchup as catchup

        job = AsyncMock()
        with patch.object(catchup, "_due_jobs", return_value=[job]):
            await catchup.run_periodic_catchup()
        job.assert_awaited_once()


class TestSessionRelease:
    """D6 — 대상 조회 세션이 발송 내내 커넥션을 잡고 있지 않는다."""

    async def test_commits_before_fan_out(self):
        from app.core.job_runner import run_per_user

        order: list[str] = []
        db = AsyncMock()
        db.commit = AsyncMock(side_effect=lambda: order.append("commit"))

        async def handle(*_args):
            order.append("handle")

        user = SimpleNamespace(id=uuid.uuid4(), email="u@e.com")
        await run_per_user(
            [(user, SimpleNamespace(notification_email=None))],
            handle,
            concurrency=1,
            failure_event="x",
            release_session=db,
        )
        assert order == ["commit", "handle"]

    async def test_without_session_still_runs(self):
        from app.core.job_runner import run_per_user

        handle = AsyncMock()
        user = SimpleNamespace(id=uuid.uuid4(), email="u@e.com")
        await run_per_user([(user, SimpleNamespace(notification_email=None))], handle, concurrency=1, failure_event="x")
        handle.assert_awaited_once()


class TestRealizedTruncation:
    """D8 — 10페이지에서 잘린 합계를 정확한 값처럼 쓰지 않는다."""

    async def _pnl(self, summary: dict | None):
        from app.kis.realized import get_overseas_realized_pnl

        page = {
            "output1": [{"ovrs_pdno": "AAPL", "trad_day": "20260101", "slcl_qty": "1", "ovrs_rlzt_pfls_amt": "100"}],
            "output2": summary if summary is not None else [],
            "ctx_area_fk200": "F",
        }
        counter = {"n": 0}

        async def _request(*_args, **_kwargs):
            counter["n"] += 1
            return {**page, "ctx_area_nk200": f"N{counter['n']}"}

        with patch("app.kis.realized.kis_request", new=_request):
            return await get_overseas_realized_pnl(
                "k", "s", "t", "1234567801", datetime(2026, 1, 1), datetime(2026, 11, 5)
            )

    async def test_truncated_without_summary(self):
        result = await self._pnl(None)
        assert result["truncated"] is True

    async def test_summary_total_is_reliable(self):
        result = await self._pnl({"ovrs_rlzt_pfls_tot_amt": "5000"})
        assert result["truncated"] is False
        assert result["total_krw"] == 5000.0


class TestOverseasCacheUnknownDeposit:
    """D9 — 국내 전용 KIS 계좌가 동기화마다 해외 3회 조회하지 않고, 수동 달러 예수금도 지우지 않는다."""

    async def test_second_sync_skips_fetch_and_keeps_deposit_unknown(self):
        from app.providers._overseas_cache import fetch_overseas_cached

        stored: dict[str, str] = {}
        cache = MagicMock()
        cache.get = AsyncMock(side_effect=lambda key: stored.get(key))
        cache.setex = AsyncMock(side_effect=lambda key, _ttl, value: stored.__setitem__(key, value))
        fetch = AsyncMock(return_value={"positions": [], "total_value_usd": 0.0, "deposit_usd": None})
        account_id = uuid.uuid4()

        for _ in range(2):
            result = await fetch_overseas_cached(
                fetch, account_id, cache, token_expired_exc=RuntimeError, broker_name="KIS"
            )

        assert fetch.await_count == 1
        assert result["deposit_usd"] is None
        assert result["positions"] == []

    async def test_holdings_are_still_fetched_every_time(self):
        from app.providers._overseas_cache import fetch_overseas_cached

        stored: dict[str, str] = {}
        cache = MagicMock()
        cache.get = AsyncMock(side_effect=lambda key: stored.get(key))
        cache.setex = AsyncMock(side_effect=lambda key, _ttl, value: stored.__setitem__(key, value))
        fetch = AsyncMock(return_value={"positions": [{"ticker": "AAPL"}], "total_value_usd": 1.0, "deposit_usd": None})
        account_id = uuid.uuid4()

        for _ in range(2):
            await fetch_overseas_cached(fetch, account_id, cache, token_expired_exc=RuntimeError, broker_name="KIS")

        assert fetch.await_count == 2


class TestAccountDeactivation:
    """D10 — 수정 경로로 비활성화하면 자동화 중단·자격증명 삭제 정리를 건너뛴다."""

    async def test_put_rejects_is_active_false(self):
        from app.api.v1 import assets
        from app.exceptions import BadRequestError
        from app.schemas.asset import AssetAccountUpdate

        with (
            patch.object(assets, "_get_owned_account", new=AsyncMock(return_value=SimpleNamespace())),
            pytest.raises(BadRequestError),
        ):
            await assets.update_account(
                account_id=uuid.uuid4(),
                req=AssetAccountUpdate(is_active=False),
                current_user=SimpleNamespace(id=uuid.uuid4()),
                db=AsyncMock(),
            )
