"""거래·계좌 수정에서 지운 값이 실제로 지워지는지(plans/109 D2) — 안 보낸 항목은 유지(구버전 APK 호환)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.transaction import TransactionUpdate


def _tx() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        transaction_type="DEPOSIT",
        amount=1000,
        transaction_date=None,
        ticker="005930",
        notes="메모",
        fee=350,
    )


class TestTransactionUpdateClears:
    @staticmethod
    async def _update(req: TransactionUpdate) -> SimpleNamespace:
        from app.api.v1 import transactions as api

        tx = _tx()
        db = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        with (
            patch.object(api, "_get_owned_tx", new=AsyncMock(return_value=tx)),
            patch.object(api, "_invalidate_tx_caches", new=AsyncMock()),
        ):
            await api.update_transaction.__wrapped__(
                request=MagicMock(), tx_id=tx.id, req=req, current_user=SimpleNamespace(id=uuid.uuid4()), db=db
            )
        return tx

    @pytest.mark.asyncio
    async def test_explicit_null_clears_optional_fields(self):
        tx = await self._update(TransactionUpdate(notes=None, fee=None, ticker=None))

        assert tx.notes is None
        assert tx.fee is None
        assert tx.ticker is None

    @pytest.mark.asyncio
    async def test_omitted_fields_are_kept(self):
        tx = await self._update(TransactionUpdate(amount=2000))

        assert tx.amount == 2000
        assert tx.notes == "메모"
        assert tx.fee == 350
        assert tx.ticker == "005930"


class TestAccountUpdateClears:
    def test_clearable_set_excludes_money_fields(self):
        from app.api.v1.assets import _CLEARABLE_ACCOUNT_FIELDS

        assert {"notes", "institution", "investment_horizon"} == _CLEARABLE_ACCOUNT_FIELDS
