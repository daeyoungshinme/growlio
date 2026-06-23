"""도메인 공통 상수.

서비스 레이어 전역에서 공유되는 불변 상수를 정의한다.
도메인별로 다른 정의가 필요한 경우(예: tax_service의 KONEX 포함 집합)는 해당 모듈에 유지한다.
"""

from __future__ import annotations

DOMESTIC_MARKETS: frozenset[str] = frozenset({"KOSPI", "KOSDAQ", "KRX"})
"""국내 주식 시장 코드. 해외 vs 국내 분류 및 Yahoo Finance 심볼 변환에 사용."""
