"""시장 신호 응답 스키마 — 종합 판단(plans/137 B). 복합 신호 본체는 dict 그대로 내려간다."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class MarketOutlook(BaseModel):
    """매크로 위험 등급 × 3대 지수 추세 종합 판단 — 표시 전용(자동 실행 게이트·전술 국면 미사용)."""

    verdict: Literal["FAVORABLE", "STEADY", "CAUTION", "DEFENSIVE", "UNKNOWN"]
    label: str
    action: str
    macro_level: Literal["GREEN", "YELLOW", "RED"] | None = None
    trend_breadth: Literal["UP", "MIXED", "DOWN"] | None = None
    trend_up_count: int = 0
    trend_known_count: int = 0
    trends: dict[str, Literal["UP", "NEUTRAL", "DOWN", "UNKNOWN"]] = {}
    deepest_drawdown_pct: float | None = None
    reasons: list[str] = []
