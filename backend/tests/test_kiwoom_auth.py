"""kiwoom/auth.py 단위 테스트 — expires_dt 포맷 파싱(YYYYMMDDHHMMSS, 구분자 없음)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.kiwoom.auth import _fetch_and_store_token


class TestFetchAndStoreTokenExpiresDt:
    @pytest.mark.asyncio
    async def test_parses_actual_kiwoom_expires_dt_format(self, override_settings, mock_cache, mock_db):
        """키움 API는 expires_dt를 'YYYYMMDDHHMMSS'(구분자 없음, KST 벽시계 값)로 응답한다 —
        'YYYY-MM-DD HH:MM:SS' 포맷을 가정하면 ValueError로 동기화 전체가 실패하고,
        KST→UTC 변환 없이 그대로 UTC로 태깅하면 만료시각이 실제보다 9시간 늦게 저장된다."""
        response = httpx.Response(
            200,
            json={"return_code": 0, "token": "kiwoom-token", "expires_dt": "20260721231120"},
            request=httpx.Request("POST", "https://example.com/oauth2/token"),
        )
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)

        with patch("app.kiwoom.auth._get_client", return_value=client):
            token = await _fetch_and_store_token(
                "app-key",
                "app-secret",
                is_mock=True,
                cache=mock_cache,
                db=mock_db,
                user_id=str(uuid.uuid4()),
                account_id=str(uuid.uuid4()),
            )

        assert token == "kiwoom-token"
        mock_db.execute.assert_awaited_once()
        insert_stmt = mock_db.execute.await_args.args[0]
        expires_at = insert_stmt.compile().params["expires_at"]
        # KST 23:11:20 == UTC 14:11:20 (같은 날, 9시간 차)
        assert expires_at == datetime(2026, 7, 21, 14, 11, 20, tzinfo=UTC)
