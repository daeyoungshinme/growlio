"""rebalancing_plan.py(인증) / rebalancing_plan_public.py(비인증) 엔드포인트 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def _make_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="test@example.com",
        display_name="테스트",
        is_active=True,
        needs_password_reset=False,
    )


def _make_mock_db():
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=None)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.get = AsyncMock(return_value=None)
    return db


def _setup_authenticated_app(user, db):
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    async def override_auth():
        return user

    async def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    return app


def _setup_public_app(db):
    from app.core.database import get_db
    from app.main import app

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    return app


def _teardown_app():
    from app.main import app

    app.dependency_overrides.clear()


def _make_leg(*, side="BUY", status="PENDING", plan_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        plan_id=plan_id or uuid.uuid4(),
        side=side,
        status=status,
        deadline_at=datetime.now(tz=UTC) + timedelta(minutes=10),
        decided_at=None,
        decided_by=None,
        execution_id=None,
        error_message=None,
        token_consumed_at=None,
        items=[],
    )


# ── 인증 필요 (rebalancing_plan.py) ────────────────────────────


class TestListPlans:
    def test_returns_leg_summaries(self):
        user = _make_user()
        db = _make_mock_db()
        leg = _make_leg()
        plan = SimpleNamespace(id=leg.plan_id, portfolio_id=uuid.uuid4(), account_id=None)

        with patch(
            "app.api.v1.rebalancing_plan.list_recent_plan_legs",
            new=AsyncMock(return_value=[(leg, plan, "포트폴리오", None)]),
        ):
            app = _setup_authenticated_app(user, db)
            client = TestClient(app)
            try:
                resp = client.get("/api/v1/rebalancing/plans")
            finally:
                _teardown_app()

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["side"] == "BUY"
        assert body[0]["portfolio_name"] == "포트폴리오"


class TestCancelPlanLeg:
    def test_returns_404_when_not_owned(self):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)

        app = _setup_authenticated_app(user, db)
        client = TestClient(app)
        try:
            resp = client.post(f"/api/v1/rebalancing/plans/{uuid.uuid4()}/legs/{uuid.uuid4()}/cancel")
        finally:
            _teardown_app()

        assert resp.status_code == 404

    def test_cancels_buy_leg(self):
        user = _make_user()
        db = _make_mock_db()
        leg = _make_leg(side="BUY")
        db.scalar = AsyncMock(return_value=leg)

        with patch("app.api.v1.rebalancing_plan.cancel_buy_leg", new=AsyncMock()) as mock_cancel:
            app = _setup_authenticated_app(user, db)
            client = TestClient(app)
            try:
                resp = client.post(f"/api/v1/rebalancing/plans/{leg.plan_id}/legs/{leg.id}/cancel")
            finally:
                _teardown_app()

        assert resp.status_code == 200
        assert resp.json()["status"] == "CANCELED"
        mock_cancel.assert_called_once()

    def test_rejects_sell_leg(self):
        user = _make_user()
        db = _make_mock_db()
        leg = _make_leg(side="SELL")
        db.scalar = AsyncMock(return_value=leg)

        with patch("app.api.v1.rebalancing_plan.reject_sell_leg", new=AsyncMock()) as mock_reject:
            app = _setup_authenticated_app(user, db)
            client = TestClient(app)
            try:
                resp = client.post(f"/api/v1/rebalancing/plans/{leg.plan_id}/legs/{leg.id}/cancel")
            finally:
                _teardown_app()

        assert resp.status_code == 200
        assert resp.json()["status"] == "REJECTED"
        mock_reject.assert_called_once()


class TestApprovePlanLeg:
    def test_approves_buy_leg(self):
        """앱에서 매수 대기시간을 건너뛰고 즉시 실행 — approve_buy_leg 경로."""
        user = _make_user()
        db = _make_mock_db()
        leg = _make_leg(side="BUY")
        db.scalar = AsyncMock(return_value=leg)

        with patch(
            "app.api.v1.rebalancing_plan.approve_buy_leg", new=AsyncMock(return_value=uuid.uuid4())
        ) as mock_approve:
            app = _setup_authenticated_app(user, db)
            client = TestClient(app)
            try:
                resp = client.post(f"/api/v1/rebalancing/plans/{leg.plan_id}/legs/{leg.id}/approve")
            finally:
                _teardown_app()

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "EXECUTED"
        assert "매수" in body["message"]
        mock_approve.assert_called_once()

    def test_approves_sell_leg(self):
        user = _make_user()
        db = _make_mock_db()
        leg = _make_leg(side="SELL")
        db.scalar = AsyncMock(return_value=leg)

        with patch(
            "app.api.v1.rebalancing_plan.approve_sell_leg", new=AsyncMock(return_value=uuid.uuid4())
        ) as mock_approve:
            app = _setup_authenticated_app(user, db)
            client = TestClient(app)
            try:
                resp = client.post(f"/api/v1/rebalancing/plans/{leg.plan_id}/legs/{leg.id}/approve")
            finally:
                _teardown_app()

        assert resp.status_code == 200
        assert resp.json()["status"] == "EXECUTED"
        mock_approve.assert_called_once()

    def test_reports_failure_when_execution_id_none(self):
        user = _make_user()
        db = _make_mock_db()
        leg = _make_leg(side="SELL")
        db.scalar = AsyncMock(return_value=leg)

        with patch("app.api.v1.rebalancing_plan.approve_sell_leg", new=AsyncMock(return_value=None)):
            app = _setup_authenticated_app(user, db)
            client = TestClient(app)
            try:
                resp = client.post(f"/api/v1/rebalancing/plans/{leg.plan_id}/legs/{leg.id}/approve")
            finally:
                _teardown_app()

        assert resp.status_code == 200
        assert resp.json()["status"] == "FAILED"


# ── 인증 없음 (rebalancing_plan_public.py) ─────────────────────


class TestPreviewPlanAction:
    def test_returns_not_found_for_unknown_token(self):
        db = _make_mock_db()

        with patch("app.api.v1.rebalancing_plan_public.get_plan_leg_by_token", new=AsyncMock(return_value=None)):
            app = _setup_public_app(db)
            client = TestClient(app)
            try:
                resp = client.get("/api/v1/rebalancing/plan-actions/bogus-token")
            finally:
                _teardown_app()

        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert body["reason"] == "NOT_FOUND"

    def test_returns_actionable_preview_for_pending_leg(self):
        db = _make_mock_db()
        leg = _make_leg(side="BUY")
        plan = SimpleNamespace(id=leg.plan_id, portfolio_id=None, account_id=None)
        leg.plan = plan

        with patch("app.api.v1.rebalancing_plan_public.get_plan_leg_by_token", new=AsyncMock(return_value=leg)):
            app = _setup_public_app(db)
            client = TestClient(app)
            try:
                resp = client.get("/api/v1/rebalancing/plan-actions/valid-token")
            finally:
                _teardown_app()

        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["actionable"] is True
        assert body["leg"]["side"] == "BUY"

    def test_get_does_not_mutate_db(self):
        """GET은 부작용이 없어야 한다 — db.commit()이 호출되지 않아야 함."""
        db = _make_mock_db()
        leg = _make_leg(side="BUY")
        leg.plan = SimpleNamespace(id=leg.plan_id, portfolio_id=None, account_id=None)

        with patch("app.api.v1.rebalancing_plan_public.get_plan_leg_by_token", new=AsyncMock(return_value=leg)):
            app = _setup_public_app(db)
            client = TestClient(app)
            try:
                client.get("/api/v1/rebalancing/plan-actions/valid-token")
            finally:
                _teardown_app()

        db.commit.assert_not_called()


class TestCancelBuyByToken:
    def test_returns_404_for_unknown_token(self):
        db = _make_mock_db()

        with patch("app.api.v1.rebalancing_plan_public.get_plan_leg_by_token", new=AsyncMock(return_value=None)):
            app = _setup_public_app(db)
            client = TestClient(app)
            try:
                resp = client.post("/api/v1/rebalancing/plan-actions/bogus-token/buy/cancel")
            finally:
                _teardown_app()

        assert resp.status_code == 404

    def test_cancels_valid_buy_leg(self):
        db = _make_mock_db()
        leg = _make_leg(side="BUY")

        with (
            patch("app.api.v1.rebalancing_plan_public.get_plan_leg_by_token", new=AsyncMock(return_value=leg)),
            patch("app.api.v1.rebalancing_plan_public.cancel_buy_leg", new=AsyncMock()) as mock_cancel,
        ):
            app = _setup_public_app(db)
            client = TestClient(app)
            try:
                resp = client.post("/api/v1/rebalancing/plan-actions/valid-token/buy/cancel")
            finally:
                _teardown_app()

        assert resp.status_code == 200
        assert resp.json()["status"] == "CANCELED"
        mock_cancel.assert_called_once()


class TestDecideSellByToken:
    def test_returns_404_for_unknown_token(self):
        db = _make_mock_db()

        with patch("app.api.v1.rebalancing_plan_public.get_plan_leg_by_token", new=AsyncMock(return_value=None)):
            app = _setup_public_app(db)
            client = TestClient(app)
            try:
                resp = client.post(
                    "/api/v1/rebalancing/plan-actions/bogus-token/sell/decision", json={"decision": "APPROVE"}
                )
            finally:
                _teardown_app()

        assert resp.status_code == 404

    def test_approve_executes_and_returns_executed(self):
        db = _make_mock_db()
        leg = _make_leg(side="SELL")

        with (
            patch("app.api.v1.rebalancing_plan_public.get_plan_leg_by_token", new=AsyncMock(return_value=leg)),
            patch(
                "app.api.v1.rebalancing_plan_public.approve_sell_leg", new=AsyncMock(return_value=uuid.uuid4())
            ) as mock_approve,
        ):
            app = _setup_public_app(db)
            client = TestClient(app)
            try:
                resp = client.post(
                    "/api/v1/rebalancing/plan-actions/valid-token/sell/decision", json={"decision": "APPROVE"}
                )
            finally:
                _teardown_app()

        assert resp.status_code == 200
        assert resp.json()["status"] == "EXECUTED"
        mock_approve.assert_called_once()

    def test_reject_does_not_execute(self):
        db = _make_mock_db()
        leg = _make_leg(side="SELL")

        with (
            patch("app.api.v1.rebalancing_plan_public.get_plan_leg_by_token", new=AsyncMock(return_value=leg)),
            patch("app.api.v1.rebalancing_plan_public.reject_sell_leg", new=AsyncMock()) as mock_reject,
            patch("app.api.v1.rebalancing_plan_public.approve_sell_leg", new=AsyncMock()) as mock_approve,
        ):
            app = _setup_public_app(db)
            client = TestClient(app)
            try:
                resp = client.post(
                    "/api/v1/rebalancing/plan-actions/valid-token/sell/decision", json={"decision": "REJECT"}
                )
            finally:
                _teardown_app()

        assert resp.status_code == 200
        assert resp.json()["status"] == "REJECTED"
        mock_reject.assert_called_once()
        mock_approve.assert_not_called()
