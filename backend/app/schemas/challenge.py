"""적립식 투자 챌린지 스키마 (challenges.py 라우터 전용)."""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, field_validator, model_validator

from app.models.challenge import (
    CHALLENGE_DEPOSIT,
    CHALLENGE_STATUSES,
    CHALLENGE_TYPES,
)
from app.schemas._validators import validate_non_negative_amount

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _validate_month(v: str | None) -> str | None:
    if v is not None and not _MONTH_RE.match(v):
        raise ValueError("월 형식은 YYYY-MM 이어야 합니다")
    return v


class ChallengeBase(BaseModel):
    title: str
    challenge_type: str
    target_amount: float | None = None
    target_pct: float | None = None
    target_months: int | None = None
    account_id: uuid.UUID | None = None
    start_month: str
    deadline_month: str | None = None
    reminder_enabled: bool = True

    @field_validator("title")
    @classmethod
    def _validate_title(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 100):
            raise ValueError("제목은 1~100자여야 합니다")
        return v

    @field_validator("challenge_type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        if v not in CHALLENGE_TYPES:
            raise ValueError("지원하지 않는 챌린지 유형입니다")
        return v

    @field_validator("target_amount")
    @classmethod
    def _validate_amount(cls, v: float | None) -> float | None:
        return validate_non_negative_amount(v)

    @field_validator("target_pct")
    @classmethod
    def _validate_pct(cls, v: float | None) -> float | None:
        if v is not None and not (-100 <= v <= 1000):
            raise ValueError("목표 수익률은 -100~1000% 범위여야 합니다")
        return v

    @field_validator("target_months")
    @classmethod
    def _validate_months(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 600):
            raise ValueError("연속 목표 개월수는 1~600 범위여야 합니다")
        return v

    @field_validator("start_month", "deadline_month")
    @classmethod
    def _validate_month_fields(cls, v: str | None) -> str | None:
        return _validate_month(v)

    @model_validator(mode="after")
    def _validate_type_targets(self) -> ChallengeBase:
        if self.challenge_type == CHALLENGE_DEPOSIT:
            if self.target_pct is not None:
                raise ValueError("입금 챌린지에는 목표 수익률을 설정할 수 없습니다")
        else:
            if self.account_id is not None:
                raise ValueError("수익률/평가금액 챌린지는 전체 투자자산 기준만 지원합니다")
            if self.target_months is not None:
                raise ValueError("이 유형에는 연속 목표 개월수를 설정할 수 없습니다")
        if self.challenge_type == "RETURN_PCT" and self.target_pct is None:
            raise ValueError("수익률 챌린지에는 목표 수익률이 필요합니다")
        if self.challenge_type == "TARGET_VALUE" and not self.target_amount:
            raise ValueError("평가금액 챌린지에는 목표 금액이 필요합니다")
        return self


class ChallengeCreate(ChallengeBase):
    pass


class ChallengeUpdate(BaseModel):
    title: str | None = None
    target_amount: float | None = None
    target_pct: float | None = None
    target_months: int | None = None
    deadline_month: str | None = None
    reminder_enabled: bool | None = None
    status: str | None = None

    @field_validator("title")
    @classmethod
    def _validate_title(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not (1 <= len(v) <= 100):
            raise ValueError("제목은 1~100자여야 합니다")
        return v

    @field_validator("deadline_month")
    @classmethod
    def _validate_month_fields(cls, v: str | None) -> str | None:
        return _validate_month(v)

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in CHALLENGE_STATUSES:
            raise ValueError("지원하지 않는 상태입니다")
        return v


class ChallengeMonth(BaseModel):
    month: str  # "2026-01"
    net_krw: float
    satisfied: bool  # 순입금 > 0
    target_met: bool  # 순입금 >= target_amount (target_amount 없으면 satisfied와 동일)


class ChallengeProgress(BaseModel):
    progress_pct: float | None = None
    current_streak: int = 0
    longest_streak: int = 0
    this_month_net_krw: float = 0.0
    this_month_satisfied: bool = False
    this_month_target_met: bool = False
    current_value_krw: float | None = None
    current_return_pct: float | None = None
    months: list[ChallengeMonth] = []


class ChallengeResponse(BaseModel):
    id: uuid.UUID
    title: str
    challenge_type: str
    target_amount: float | None
    target_pct: float | None
    target_months: int | None
    account_id: uuid.UUID | None
    start_month: str
    deadline_month: str | None
    reminder_enabled: bool
    status: str
    completed_at: str | None
    created_at: str
    progress: ChallengeProgress


class ChallengeSummary(BaseModel):
    needs_attention: bool
    count: int  # 이번 달 미충족 상태인 ACTIVE 입금 챌린지 수
