"""도메인 공통 상수.

서비스 레이어 전역에서 공유되는 불변 상수를 정의한다.
도메인별로 다른 정의가 필요한 경우(예: tax_service의 KONEX 포함 집합)는 해당 모듈에 유지한다.
"""

from __future__ import annotations

DOMESTIC_MARKETS: frozenset[str] = frozenset({"KOSPI", "KOSDAQ", "KRX"})
"""국내 주식 시장 코드. 해외 vs 국내 분류 및 Yahoo Finance 심볼 변환에 사용."""

CASH_EQUIVALENT_TICKER: str = "CASH_EQUIVALENT"
CASH_EQUIVALENT_NAME: str = "현금성 자산 (CMA·파킹통장 등)"
CASH_EQUIVALENT_MARKET: str = "CASH"
"""실제 시세 없는 현금성 자산 합성 sentinel. 목표 역산 추천(goal_recommendation_service)과
포트폴리오 목표 항목(rebalancing/service.py) 양쪽에서 동일 문자열을 공유해야 하므로 여기서 단일 정의."""

CASH_EQUIVALENT_ACCOUNT_TYPES: frozenset[str] = frozenset({"BANK_ACCOUNT", "DEPOSIT"})
"""CASH_EQUIVALENT 포트폴리오 항목의 현재가치를 집계할 때 합산 대상이 되는 계좌 asset_type
(CMA·파킹통장·예적금 등 은행성 계좌). CASH_OTHER는 제외 — 개별 종목(Position)을 보유할 수 있는
브로커성 계좌이므로 portfolio_service.STOCK_TYPES 쪽에서 종목 단위로 추적된다."""

TOKEN_CACHE_TTL_BUFFER: int = 300  # 만료 5분 전 갱신 — KIS/키움 토큰 갱신 공용(app/kis/auth.py, app/kiwoom/auth.py)
