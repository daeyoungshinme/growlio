"""적립식 투자 챌린지 서비스 테스트 — 스트릭 계산 + 진행률."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import challenge_service as cs


def _ns(**kw):
    base = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="테스트 챌린지",
        challenge_type="DEPOSIT",
        target_amount=None,
        target_pct=None,
        target_months=None,
        account_id=None,
        start_month="2026-01",
        deadline_month=None,
        reminder_enabled=True,
        status="ACTIVE",
        completed_at=None,
        created_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestMonthHelpers:
    def test_add_months(self):
        assert cs._add_months("2026-01", 1) == "2026-02"
        assert cs._add_months("2026-12", 1) == "2027-01"
        assert cs._add_months("2026-03", -3) == "2025-12"

    def test_iter_months_inclusive(self):
        assert cs._iter_months("2026-01", "2026-03") == ["2026-01", "2026-02", "2026-03"]

    def test_iter_months_empty_when_start_after_end(self):
        assert cs._iter_months("2026-05", "2026-03") == []


class TestComputeStreaks:
    def test_three_consecutive_months(self):
        net = {"2026-01": 100.0, "2026-02": 100.0, "2026-03": 100.0}
        current, longest = cs._compute_streaks(net, "2026-01", "2026-03")
        assert current == 3
        assert longest == 3

    def test_gap_month_breaks_current_streak_but_longest_keeps_earlier_run(self):
        net = {"2026-01": 100.0, "2026-02": 100.0, "2026-03": 0.0, "2026-04": 100.0}
        current, longest = cs._compute_streaks(net, "2026-01", "2026-04")
        assert current == 1  # 04만
        assert longest == 2  # 01-02

    def test_in_progress_current_month_without_deposit_does_not_break(self):
        # 이번 달(2026-04) 아직 미입금이지만 직전까지 연속 3개월이면 스트릭 유지
        net = {"2026-01": 100.0, "2026-02": 100.0, "2026-03": 100.0}
        current, _ = cs._compute_streaks(net, "2026-01", "2026-04")
        assert current == 3

    def test_current_month_deposit_extends_streak(self):
        net = {"2026-01": 100.0, "2026-02": 100.0, "2026-03": 100.0, "2026-04": 100.0}
        current, _ = cs._compute_streaks(net, "2026-01", "2026-04")
        assert current == 4

    def test_negative_net_counts_as_miss(self):
        net = {"2026-01": 100.0, "2026-02": -50.0, "2026-03": 100.0}
        current, longest = cs._compute_streaks(net, "2026-01", "2026-03")
        assert current == 1
        assert longest == 1

    def test_start_month_clips_window(self):
        net = {"2025-01": 100.0, "2026-02": 100.0, "2026-03": 100.0}
        current, longest = cs._compute_streaks(net, "2026-01", "2026-03")
        # 2025-01은 윈도우 밖 → 2026-01 미입금이므로 최근 연속은 02-03
        assert current == 2
        assert longest == 2

    def test_empty_window(self):
        assert cs._compute_streaks({}, "2026-05", "2026-03") == (0, 0)


class TestBuildMonths:
    def test_target_met_requires_target_amount(self):
        net = {"2026-01": 300.0, "2026-02": 600.0}
        months = cs._build_months(net, "2026-01", "2026-02", target_amount=500.0)
        assert months[0].satisfied is True
        assert months[0].target_met is False
        assert months[1].target_met is True

    def test_no_target_amount_target_met_equals_satisfied(self):
        net = {"2026-01": 1.0}
        months = cs._build_months(net, "2026-01", "2026-01", target_amount=None)
        assert months[0].target_met is True


def _mock_db_with_net(net: dict[str, float]) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = [SimpleNamespace(month=k, net=v) for k, v in net.items()]
    db.execute = AsyncMock(return_value=result)
    return db


class TestComputeProgressDeposit:
    @pytest.mark.asyncio
    async def test_deposit_progress_with_target_months(self):
        challenge = _ns(challenge_type="DEPOSIT", target_months=6, start_month="2026-01")
        db = _mock_db_with_net({"2026-01": 500000.0, "2026-02": 500000.0})
        with patch.object(cs, "_now_kst_date", return_value=__import__("datetime").date(2026, 3, 15)):
            progress = await cs.compute_progress(challenge, challenge.user_id, db)
        assert progress.current_streak == 2
        assert progress.progress_pct == pytest.approx(33.3, abs=0.1)
        assert progress.this_month_satisfied is False

    @pytest.mark.asyncio
    async def test_deposit_progress_open_ended_has_no_progress_pct(self):
        challenge = _ns(challenge_type="DEPOSIT", target_months=None, start_month="2026-01")
        db = _mock_db_with_net({"2026-01": 100.0})
        with patch.object(cs, "_now_kst_date", return_value=__import__("datetime").date(2026, 1, 20)):
            progress = await cs.compute_progress(challenge, challenge.user_id, db)
        assert progress.progress_pct is None
        assert progress.current_streak == 1


class TestComputeProgressOther:
    @pytest.mark.asyncio
    async def test_return_pct_progress(self):
        challenge = _ns(challenge_type="RETURN_PCT", target_pct=10.0)
        db = AsyncMock()
        summary = {"xirr_pct": 5.0, "annual_return_pct": None, "cumulative_return_pct": None}
        with patch("app.services.asset_aggregator.get_dashboard_summary", AsyncMock(return_value=summary)):
            progress = await cs.compute_progress(challenge, challenge.user_id, db)
        assert progress.current_return_pct == 5.0
        assert progress.progress_pct == 50.0

    @pytest.mark.asyncio
    async def test_target_value_progress(self):
        challenge = _ns(challenge_type="TARGET_VALUE", target_amount=100_000_000.0)
        db = AsyncMock()
        with patch.object(cs, "build_asset_totals", AsyncMock(return_value=(50_000_000.0, 0, 0, {}))):
            progress = await cs.compute_progress(challenge, challenge.user_id, db)
        assert progress.current_value_krw == 50_000_000.0
        assert progress.progress_pct == 50.0


class TestChallengeSummary:
    @pytest.mark.asyncio
    async def test_needs_attention_when_unmet_and_late_in_month(self):
        challenge = _ns(challenge_type="DEPOSIT")
        db = AsyncMock()
        scalars_result = MagicMock()
        scalars_result.scalars.return_value.all.return_value = [challenge]
        net_result = MagicMock()
        net_result.all.return_value = []  # 이번 달 입금 없음

        db.execute = AsyncMock(side_effect=[scalars_result, net_result])
        with patch.object(cs, "_now_kst_date", return_value=__import__("datetime").date(2026, 3, 25)):
            summary = await cs.get_challenge_summary(challenge.user_id, db)
        assert summary.needs_attention is True
        assert summary.count == 1

    @pytest.mark.asyncio
    async def test_no_attention_early_in_month(self):
        challenge = _ns(challenge_type="DEPOSIT")
        db = AsyncMock()
        scalars_result = MagicMock()
        scalars_result.scalars.return_value.all.return_value = [challenge]
        net_result = MagicMock()
        net_result.all.return_value = []
        db.execute = AsyncMock(side_effect=[scalars_result, net_result])
        with patch.object(cs, "_now_kst_date", return_value=__import__("datetime").date(2026, 3, 5)):
            summary = await cs.get_challenge_summary(challenge.user_id, db)
        assert summary.needs_attention is False
        assert summary.count == 1


class TestListAndSerialize:
    @pytest.mark.asyncio
    async def test_list_challenges_with_progress_serializes(self, mock_cache):
        import datetime as _dt

        challenge = _ns(
            challenge_type="DEPOSIT",
            target_months=6,
            start_month="2026-01",
            created_at=_dt.datetime.now(_dt.UTC),
        )
        db = AsyncMock()
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [challenge]
        net_result = MagicMock()
        net_result.all.return_value = [SimpleNamespace(month="2026-01", net=100.0)]
        db.execute = AsyncMock(side_effect=[list_result, net_result])
        mock_cache.get = AsyncMock(return_value=None)
        with patch.object(cs, "_now_kst_date", return_value=_dt.date(2026, 2, 10)):
            out = await cs.list_challenges_with_progress(challenge.user_id, db, mock_cache)
        assert len(out) == 1
        assert out[0].title == "테스트 챌린지"
        assert out[0].progress.current_streak == 1
        mock_cache.setex.assert_awaited()

    @pytest.mark.asyncio
    async def test_list_returns_cached(self, mock_cache):
        cached = [
            {
                "id": str(uuid.uuid4()),
                "title": "캐시된 챌린지",
                "challenge_type": "DEPOSIT",
                "target_amount": None,
                "target_pct": None,
                "target_months": None,
                "account_id": None,
                "start_month": "2026-01",
                "deadline_month": None,
                "reminder_enabled": True,
                "status": "ACTIVE",
                "completed_at": None,
                "created_at": "2026-01-01T00:00:00+00:00",
                "progress": {"current_streak": 3, "longest_streak": 3, "months": []},
            }
        ]
        import json

        mock_cache.get = AsyncMock(return_value=json.dumps(cached))
        db = AsyncMock()
        out = await cs.list_challenges_with_progress(uuid.uuid4(), db, mock_cache)
        assert out[0].title == "캐시된 챌린지"
        db.execute.assert_not_called()


class TestCrud:
    @pytest.mark.asyncio
    async def test_create_challenge_commits_and_invalidates(self, mock_cache):
        from app.schemas.challenge import ChallengeCreate

        db = AsyncMock()
        db.add = MagicMock()
        payload = ChallengeCreate(
            title="매달 50만원", challenge_type="DEPOSIT", target_amount=500000, start_month="2026-01"
        )
        uid = uuid.uuid4()
        challenge = await cs.create_challenge(uid, db, payload, mock_cache)
        assert challenge.title == "매달 50만원"
        db.add.assert_called_once()
        db.commit.assert_awaited()
        mock_cache.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_challenge_sets_completed_at_on_complete(self, mock_cache):
        from app.schemas.challenge import ChallengeUpdate

        db = AsyncMock()
        challenge = _ns()
        await cs.update_challenge(challenge, db, ChallengeUpdate(status="COMPLETED"), mock_cache)
        assert challenge.status == "COMPLETED"
        assert challenge.completed_at is not None
