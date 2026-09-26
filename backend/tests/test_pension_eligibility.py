"""연금저축·IRP 매수 불가 상품 판별(goal_candidate_service.pension_ineligibility_reason) — 계획 37 E1."""

from __future__ import annotations

import pytest

from app.services.goal_candidate_service import pension_exclusion_note, pension_ineligibility_reason


def _c(ticker: str, name: str, market: str = "KOSPI") -> dict[str, str]:
    return {"ticker": ticker, "name": name, "market": market}


@pytest.mark.parametrize("tax_type", ["PENSION_SAVINGS", "IRP"])
@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (_c("069500", "KODEX 200"), None),
        (_c("133690", "TIGER 미국나스닥100"), None),
        (_c("458730", "TIGER 미국배당다우존스"), None),
        (_c("153130", "KODEX 단기채권"), None),
        (_c("379800", "RISE 미국S&P500"), None),
        (_c("122630", "KODEX 레버리지"), "레버리지·인버스 ETF"),
        (_c("252670", "KODEX 200선물인버스2X"), "레버리지·인버스 ETF"),
        (_c("123310", "TIGER 인버스"), "레버리지·인버스 ETF"),
        (_c("409820", "KODEX 미국나스닥100레버리지(합성 H)"), "레버리지·인버스 ETF"),
        (_c("500001", "신한 WTI원유 선물 ETN"), "ETN"),
        (_c("005930", "삼성전자"), "개별 종목"),
        (_c("000660", "SK하이닉스"), "개별 종목"),
        (_c("CASH_EQUIVALENT", "현금성 자산 (CMA·파킹통장 등)", "CASH"), None),
    ],
)
def test_pension_accounts_exclude_non_buyable_products(candidate, expected, tax_type):
    assert pension_ineligibility_reason(candidate, tax_type) == expected


@pytest.mark.parametrize("tax_type", ["GENERAL", "ISA", "OVERSEAS_DEDICATED"])
def test_non_pension_accounts_are_not_restricted(tax_type):
    """ISA·일반 계좌는 레버리지 ETF·개별주 매수가 가능하므로 이 필터 대상이 아니다."""
    assert pension_ineligibility_reason(_c("122630", "KODEX 레버리지"), tax_type) is None
    assert pension_ineligibility_reason(_c("005930", "삼성전자"), tax_type) is None


def test_exclusion_note_names_account_reasons_and_examples():
    excluded = [_c("005930", "삼성전자"), _c("122630", "KODEX 레버리지"), _c("000660", "SK하이닉스")]
    note = pension_exclusion_note(excluded, "IRP")
    assert note is not None
    assert note.startswith("IRP 계좌에서는")
    assert "개별 종목" in note
    assert "레버리지·인버스 ETF" in note
    assert "삼성전자, KODEX 레버리지 외 1개" in note
    assert pension_exclusion_note([], "PENSION_SAVINGS") is None
