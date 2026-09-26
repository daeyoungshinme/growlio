"""도메인 공통 상수.

서비스 레이어 전역에서 공유되는 불변 상수를 정의한다.
도메인별로 다른 정의가 필요한 경우(예: tax_service의 KONEX 포함 집합)는 해당 모듈에 유지한다.
"""

from __future__ import annotations

DOMESTIC_MARKETS: frozenset[str] = frozenset({"KOSPI", "KOSDAQ", "KRX"})
"""국내 주식 시장 코드. 해외 vs 국내 분류 및 Yahoo Finance 심볼 변환에 사용."""

POSITION_STOCK_ASSET_TYPES: frozenset[str] = frozenset({"STOCK_KIS", "STOCK_KIWOOM", "STOCK_TOSS", "STOCK_OTHER"})
"""종목(Position) 단위로 평가금·매입원가를 추적하는 증권 계좌 asset_type. 브로커를 추가하면 여기에만
추가한다 — 서비스마다 로컬 집합을 두던 시절 토스 연동(STOCK_TOSS)이 대시보드 주식평가액·자산구성·
세금·자산추이·추천드리프트 집계에서 전부 누락됐던 사고가 있었다(2026-09-25).
주문 실행 가능 집합은 별개 — rebalancing/order_builder.ORDER_EXECUTABLE_ASSET_TYPES(토스 제외)."""

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
