"""app/kis/balance.py 단위 테스트 — 국내 예수금 필드 선택(D+2)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.kis.balance import get_domestic_balance


def _balance_response(*, prvs_rcdl_excc_amt="120000", dnca_tot_amt="100000"):
    summary = {"evlu_amt_smtl_amt": "950000", "pchs_amt_smtl_amt": "900000", "evlu_pfls_smtl_amt": "50000"}
    if prvs_rcdl_excc_amt is not None:
        summary["prvs_rcdl_excc_amt"] = prvs_rcdl_excc_amt
    if dnca_tot_amt is not None:
        summary["dnca_tot_amt"] = dnca_tot_amt
    return {"output1": [], "output2": [summary]}


class TestKisDomesticDeposit:
    @pytest.mark.asyncio
    async def test_uses_prvs_rcdl_excc_amt_d2_deposit(self):
        async def _fake(*args, **kwargs):
            return _balance_response()

        with patch("app.kis.balance.kis_request", side_effect=_fake):
            result = await get_domestic_balance("k", "s", "t", "12345678", is_mock=False)

        assert result["deposit_krw"] == 120000.0  # D+2, not dnca_tot_amt(100000)

    @pytest.mark.asyncio
    async def test_falls_back_to_dnca_tot_amt_when_d2_missing(self):
        async def _fake(*args, **kwargs):
            return _balance_response(prvs_rcdl_excc_amt=None)

        with (
            patch("app.kis.balance.kis_request", side_effect=_fake),
            patch("app.kis.balance.logger") as mock_logger,
        ):
            result = await get_domestic_balance("k", "s", "t", "12345678", is_mock=False)

        assert result["deposit_krw"] == 100000.0
        mock_logger.warning.assert_called_once()
