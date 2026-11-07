"""Auth API 엔드포인트 통합 테스트 (FastAPI TestClient + DB mock)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.api_helpers import setup_app

# ── 공통 헬퍼 ────────────────────────────────────────────────


def _make_mock_db(existing_user=None):
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=existing_user)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    async def _refresh(obj):
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid.uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    return db


def _make_user(email="test@example.com"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        email=email,
        display_name="테스트 유저",
        is_active=True,
        needs_password_reset=False,
    )


def _valid_jwt_payload(user_id: str, email: str = "test@example.com") -> dict:
    return {"sub": user_id, "email": email}


# ── GET /auth/me ──────────────────────────────────────────────


class TestMe:
    """GET /api/v1/auth/me"""

    def test_me_returns_user_info(self):
        """유효한 JWT로 요청하면 유저 정보를 반환한다."""
        from app.api.deps import get_current_user
        from app.main import app

        user = _make_user()

        async def override_get_current_user():
            return user

        app.dependency_overrides[get_current_user] = override_get_current_user
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer faketoken"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["email"] == user.email
            assert "needs_password_reset" in body
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_me_without_token_returns_401(self):
        """토큰 없이 요청하면 401을 반환한다."""
        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401


# ── POST /auth/password-reset-complete ────────────────────────


class TestPasswordResetComplete:
    """재설정을 마치면 DB 플래그를 꺼야 다음 /auth/me에서 배너가 다시 뜨지 않는다."""

    def _call(self, user, db):
        from app.api.deps import get_current_user
        from app.core.database import get_db
        from app.main import app

        async def override_user():
            return user

        async def override_db():
            yield db

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                return client.post(
                    "/api/v1/auth/password-reset-complete", headers={"Authorization": "Bearer faketoken"}
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    @pytest.mark.parametrize(("initial", "commits"), [(True, 1), (False, 0)])
    def test_clears_flag(self, initial, commits):
        user = _make_user()
        user.needs_password_reset = initial
        db = _make_mock_db(existing_user=user)

        resp = self._call(user, db)

        assert resp.status_code == 200
        assert resp.json()["needs_password_reset"] is False
        assert user.needs_password_reset is False
        assert db.commit.await_count == commits

    def test_without_token_returns_401(self):
        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/auth/password-reset-complete")
        assert resp.status_code == 401


# ── POST /auth/sync-profile ───────────────────────────────────


class TestSyncProfile:
    """POST /api/v1/auth/sync-profile"""

    def test_sync_profile_creates_new_user(self):
        """신규 유저 JWT로 요청하면 users + user_settings 행을 생성한다."""
        from app.api.deps import get_token_payload
        from app.core.database import get_db
        from app.main import app

        user_id = str(uuid.uuid4())
        db = _make_mock_db(existing_user=None)

        async def override_db():
            yield db

        async def override_payload():
            return _valid_jwt_payload(user_id)

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_token_payload] = override_payload
        try:
            with (
                patch("app.api.v1.auth.supabase_user_exists", new=AsyncMock(return_value=True)),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.post(
                    "/api/v1/auth/sync-profile",
                    json={"display_name": "새유저"},
                    headers={"Authorization": "Bearer faketoken"},
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_token_payload, None)

    def test_sync_profile_concurrent_insert_returns_existing(self):
        """두 기기가 동시에 부르면 나중 insert가 PK 충돌 — 500 대신 먼저 생긴 행을 돌려준다(plans/115 A9)."""
        from sqlalchemy.exc import IntegrityError

        from app.api.deps import get_token_payload
        from app.core.database import get_db
        from app.main import app

        user_id = str(uuid.uuid4())
        winner = _make_user()
        winner.id = uuid.UUID(user_id)
        db = _make_mock_db()
        # 존재 확인 → 고아 이메일 확인은 None, 충돌 후 재조회는 먼저 만든 행
        db.scalar = AsyncMock(side_effect=[None, None, winner])
        db.commit = AsyncMock(side_effect=IntegrityError("insert", {}, Exception("duplicate key")))
        db.rollback = AsyncMock()

        async def override_db():
            yield db

        async def override_payload():
            return _valid_jwt_payload(user_id)

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_token_payload] = override_payload
        try:
            with (
                patch("app.api.v1.auth.supabase_user_exists", new=AsyncMock(return_value=True)),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.post(
                    "/api/v1/auth/sync-profile",
                    json={"display_name": "새유저"},
                    headers={"Authorization": "Bearer faketoken"},
                )
            assert resp.status_code == 200
            assert resp.json()["id"] == user_id
            db.rollback.assert_awaited_once()
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_token_payload, None)

    def test_sync_profile_invalid_payload_returns_401(self):
        """sub 또는 email 없는 페이로드로 요청하면 401을 반환한다 (line 36)."""
        from app.api.deps import get_token_payload
        from app.main import app

        async def override_payload():
            return {"sub": None, "email": None}

        app.dependency_overrides[get_token_payload] = override_payload
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/v1/auth/sync-profile",
                    json={"display_name": "테스트"},
                    headers={"Authorization": "Bearer faketoken"},
                )
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.pop(get_token_payload, None)

    def test_sync_profile_idempotent(self):
        """이미 존재하는 유저 JWT로 요청하면 기존 유저를 반환한다 (200)."""
        from app.api.deps import get_token_payload
        from app.core.database import get_db
        from app.main import app

        user_id = str(uuid.uuid4())
        existing = _make_user()
        db = _make_mock_db(existing_user=existing)

        async def override_db():
            yield db

        async def override_payload():
            return _valid_jwt_payload(user_id)

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_token_payload] = override_payload
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/v1/auth/sync-profile",
                    json={"display_name": None},
                    headers={"Authorization": "Bearer faketoken"},
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_token_payload, None)

    def test_sync_profile_cleans_up_orphan_with_same_email(self):
        """탈퇴 처리 중 로컬 DB 삭제만 실패해 남은 동일 이메일 고아 row는

        재가입(새 sub) 시 자동 삭제되고 새 유저가 정상 생성된다.
        """
        from app.api.deps import get_token_payload
        from app.core.database import get_db
        from app.main import app

        new_user_id = str(uuid.uuid4())
        email = "sdy8603@hanmail.net"
        orphan = _make_user(email=email)

        db = _make_mock_db()
        # id 조회 → None(신규), email 조회 → orphan 발견, 순서대로 반환
        db.scalar = AsyncMock(side_effect=[None, orphan])
        db.delete = AsyncMock()

        async def override_db():
            yield db

        async def override_payload():
            return _valid_jwt_payload(new_user_id, email=email)

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_token_payload] = override_payload
        try:
            with (
                # 새 sub는 Supabase에 있고(True), 옛 sub(고아)는 없다(False)
                patch("app.api.v1.auth.supabase_user_exists", new=AsyncMock(side_effect=[True, False])),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.post(
                    "/api/v1/auth/sync-profile",
                    json={"display_name": "재가입유저"},
                    headers={"Authorization": "Bearer faketoken"},
                )
            assert resp.status_code == 200
            db.delete.assert_called_once_with(orphan)
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_token_payload, None)

    def test_sync_profile_does_not_delete_live_user_sharing_email(self):
        """같은 이메일의 기존 사용자가 Supabase Auth에 아직 살아 있으면 고아가 아니다 — 지우지 않고 409."""
        from app.api.deps import get_token_payload
        from app.core.database import get_db
        from app.main import app

        email = "shared@example.com"
        existing = _make_user(email=email)
        db = _make_mock_db()
        db.scalar = AsyncMock(side_effect=[None, existing])
        db.delete = AsyncMock()

        async def override_db():
            yield db

        async def override_payload():
            return _valid_jwt_payload(str(uuid.uuid4()), email=email)

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_token_payload] = override_payload
        try:
            with (
                patch("app.api.v1.auth.supabase_user_exists", new=AsyncMock(return_value=True)),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.post(
                    "/api/v1/auth/sync-profile",
                    json={"display_name": "x"},
                    headers={"Authorization": "Bearer faketoken"},
                )
            assert resp.status_code == 409
            db.delete.assert_not_called()
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_token_payload, None)

    def _post_new_sub(self, exists_mock):
        from app.api.deps import get_token_payload
        from app.core.database import get_db
        from app.main import app

        db = _make_mock_db(existing_user=None)

        async def override_db():
            yield db

        async def override_payload():
            return _valid_jwt_payload(str(uuid.uuid4()))

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_token_payload] = override_payload
        try:
            with (
                patch("app.api.v1.auth.supabase_user_exists", new=exists_mock),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.post(
                    "/api/v1/auth/sync-profile",
                    json={"display_name": None},
                    headers={"Authorization": "Bearer faketoken"},
                )
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_token_payload, None)
        return resp, db

    def test_sync_profile_rejects_deleted_supabase_user(self):
        """탈퇴 후 다른 기기에 남은 access token으로 호출하면 계정을 되살리지 않는다 (plans/61 A5)."""
        resp, db = self._post_new_sub(AsyncMock(return_value=False))
        assert resp.status_code == 401
        db.add.assert_not_called()

    def test_sync_profile_503_when_supabase_unreachable(self):
        import httpx

        resp, db = self._post_new_sub(AsyncMock(side_effect=httpx.ConnectError("down")))
        assert resp.status_code == 503
        db.add.assert_not_called()


# ── POST /auth/account/delete ───────────────────────────────────


def test_user_settings_relationship_uses_passive_deletes():
    """UserSettings.user_id는 PK+FK라 passive_deletes 없이 User를 삭제하면 SQLAlchemy가

    FK를 NULL로 지우려다 AssertionError를 낸다 (PK는 NULL 불가). mock DB 테스트로는
    이 매퍼 설정 버그를 잡지 못하므로 매퍼 configuration 자체를 검증한다.
    """
    from sqlalchemy import inspect

    from app.models.user import User

    mapper = inspect(User)
    assert mapper.relationships["settings"].passive_deletes is True
    assert mapper.relationships["asset_accounts"].passive_deletes is True


def _configure_empty_execute(db) -> None:
    """db.execute(select(AssetAccount.id)...).scalars().all() → [] 로 체이닝 설정."""
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=execute_result)


class TestDeleteAccount:
    """POST /api/v1/auth/account/delete"""

    def test_wrong_password_returns_401(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.delete = AsyncMock()
        app = setup_app(user, db)

        with (
            patch("app.api.v1.auth.verify_password", AsyncMock(return_value=False)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(
                "/api/v1/auth/account/delete",
                json={"password": "wrong"},
                headers={"Authorization": "Bearer faketoken"},
            )

        assert resp.status_code == 401
        db.delete.assert_not_called()
        app.dependency_overrides.clear()

    def test_supabase_delete_failure_returns_502_and_keeps_local_data(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.delete = AsyncMock()
        _configure_empty_execute(db)
        app = setup_app(user, db)

        with (
            patch("app.api.v1.auth.verify_password", AsyncMock(return_value=True)),
            patch(
                "app.api.v1.auth.delete_supabase_user",
                AsyncMock(side_effect=httpx.HTTPStatusError("boom", request=MagicMock(), response=MagicMock())),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(
                "/api/v1/auth/account/delete",
                json={"password": "correct"},
                headers={"Authorization": "Bearer faketoken"},
            )

        assert resp.status_code == 502
        # 로컬 삭제는 flush만 된 상태라 되돌리면 데이터가 그대로다
        db.rollback.assert_awaited()
        db.commit.assert_not_called()
        app.dependency_overrides.clear()

    def test_success_deletes_local_user_and_returns_204(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.delete = AsyncMock()
        _configure_empty_execute(db)
        app = setup_app(user, db)

        cache_mock = AsyncMock()
        cache_mock.scan = AsyncMock(return_value=(0, []))
        cache_mock.delete = AsyncMock()

        with (
            patch("app.api.v1.auth.verify_password", AsyncMock(return_value=True)),
            patch("app.api.v1.auth.delete_supabase_user", AsyncMock(return_value=None)),
            patch("app.api.v1.auth.get_cache_store", AsyncMock(return_value=cache_mock)),
            patch("app.services.notifications.email_service.send_account_deletion_email", AsyncMock(return_value=True)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(
                "/api/v1/auth/account/delete",
                json={"password": "correct"},
                headers={"Authorization": "Bearer faketoken"},
            )

        assert resp.status_code == 204
        db.delete.assert_called_once_with(user)
        db.commit.assert_called_once()
        # plans/117 B5: FK 없는 app_state의 탈퇴자 키(만료 없는 목표 달성 기록 등)도 지운다
        from sqlalchemy.dialects import postgresql

        sqls = [
            str(c.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()
            for c in db.execute.call_args_list
        ]
        assert any(sql.startswith("delete from app_state") and str(user.id) in sql for sql in sqls)
        app.dependency_overrides.clear()

    def test_local_delete_failure_returns_502(self, override_settings):
        """Supabase 삭제는 성공했지만 로컬 DB 삭제/커밋이 실패하면 502를 반환하고

        고아 발생을 로그로 남긴다 (수동 정리는 sync_profile의 자가 치유가 처리).
        """
        user = _make_user()
        db = _make_mock_db()
        db.delete = AsyncMock()
        db.commit = AsyncMock(side_effect=RuntimeError("connection lost"))
        _configure_empty_execute(db)
        app = setup_app(user, db)

        with (
            patch("app.api.v1.auth.verify_password", AsyncMock(return_value=True)),
            patch("app.api.v1.auth.delete_supabase_user", AsyncMock(return_value=None)),
            patch("app.api.v1.auth.report_handled_failure") as report,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(
                "/api/v1/auth/account/delete",
                json={"password": "correct"},
                headers={"Authorization": "Bearer faketoken"},
            )

        assert resp.status_code == 502
        db.delete.assert_called_once_with(user)
        # 고아 데이터는 Sentry로 보고하고, 이메일은 마스킹해서 남긴다
        assert report.call_args.args[0] == "account_delete_local_cleanup_failed"
        assert report.call_args.kwargs["email"] != user.email
        app.dependency_overrides.clear()


class TestAccountDeleteOrder:
    """plans/109 C6 — 로컬 삭제가 실패할 수 있으면 Supabase를 지우기 전에 드러나야 한다."""

    def test_local_failure_keeps_supabase_user(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.delete = AsyncMock()
        db.flush = AsyncMock(side_effect=RuntimeError("fk violation"))
        db.rollback = AsyncMock()
        _configure_empty_execute(db)
        app = setup_app(user, db)
        delete_remote = AsyncMock(return_value=None)

        with (
            patch("app.api.v1.auth.verify_password", AsyncMock(return_value=True)),
            patch("app.api.v1.auth.delete_supabase_user", delete_remote),
            patch("app.api.v1.auth.report_handled_failure"),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(
                "/api/v1/auth/account/delete",
                json={"password": "correct"},
                headers={"Authorization": "Bearer faketoken"},
            )

        assert resp.status_code == 502
        delete_remote.assert_not_awaited()
        db.commit.assert_not_awaited()
        app.dependency_overrides.clear()

    def test_supabase_failure_rolls_back_local_delete(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.delete = AsyncMock()
        db.flush = AsyncMock()
        db.rollback = AsyncMock()
        _configure_empty_execute(db)
        app = setup_app(user, db)
        error = httpx.ConnectError("down")

        with (
            patch("app.api.v1.auth.verify_password", AsyncMock(return_value=True)),
            patch("app.api.v1.auth.delete_supabase_user", AsyncMock(side_effect=error)),
            patch("app.api.v1.auth.report_handled_failure"),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(
                "/api/v1/auth/account/delete",
                json={"password": "correct"},
                headers={"Authorization": "Bearer faketoken"},
            )

        assert resp.status_code == 502
        db.rollback.assert_awaited()
        db.commit.assert_not_awaited()
        app.dependency_overrides.clear()
