"""전술 배분 API 요청 스키마 (`api/v1/tactical.py`)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.services.tactical_dip import DEFAULT_DIP_SHIFT_PCT, MAX_DIP_SHIFT_PCT
from app.services.tactical_tilt import DEFAULT_TILT_SHIFT_PCT, MAX_TILT_SHIFT_PCT


class TacticalStrategyUpsert(BaseModel):
    notify_enabled: bool = True
    regime_weights: dict[str, dict[str, float]] | None = None  # None이면 기본 비중표
    # 나스닥/S&P 틸트 이동폭(%p) — 0이면 틸트 끔
    tilt_shift_pct: float = Field(DEFAULT_TILT_SHIFT_PCT, ge=0, le=MAX_TILT_SHIFT_PCT)
    # 눌림목(웅덩이) 현금 투입 최대폭(%p) — 0이면 끔
    dip_shift_pct: float = Field(DEFAULT_DIP_SHIFT_PCT, ge=0, le=MAX_DIP_SHIFT_PCT)
    # False면 매크로 신호를 무시하고 차트 추세만으로 국면 판정
    use_macro: bool = True

    @field_validator("regime_weights")
    @classmethod
    def _validate_weights(cls, v: dict[str, dict[str, float]] | None) -> dict[str, dict[str, float]] | None:
        # 지연 import — 스키마 모듈이 전술 서비스 전체(기술지표·시세 조회)를 끌고 오지 않게
        from app.services.tactical_allocation_service import validate_regime_weights

        return None if v is None else validate_regime_weights(v)


class TacticalApplyRequest(BaseModel):
    # 1이면 제안 비중 그대로, 0.5면 현재 목표에서 제안 쪽으로 절반만(분할 적용)
    fraction: float = Field(1.0, gt=0, le=1)
