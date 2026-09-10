"""적립식 투자 챌린지 — 매달 입금 습관·수익률·평가금액 목표를 추적하고 독려 알림을 보낸다."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# challenge_type 값
CHALLENGE_DEPOSIT = "DEPOSIT"  # 매달 입금 습관(연속 스트릭). target_amount(월 목표액, 선택)·target_months(연속 목표)
CHALLENGE_RETURN_PCT = "RETURN_PCT"  # 누적/연환산 수익률 목표. target_pct
CHALLENGE_TARGET_VALUE = "TARGET_VALUE"  # 투자자산 평가금액 목표. target_amount

CHALLENGE_TYPES = frozenset({CHALLENGE_DEPOSIT, CHALLENGE_RETURN_PCT, CHALLENGE_TARGET_VALUE})

# status 값
CHALLENGE_ACTIVE = "ACTIVE"
CHALLENGE_COMPLETED = "COMPLETED"
CHALLENGE_ARCHIVED = "ARCHIVED"

CHALLENGE_STATUSES = frozenset({CHALLENGE_ACTIVE, CHALLENGE_COMPLETED, CHALLENGE_ARCHIVED})


class InvestmentChallenge(Base):
    """사용자가 만든 적립식 투자 챌린지. 진행률·스트릭은 저장하지 않고 Transaction/스냅샷에서 매번 재계산."""

    __tablename__ = "investment_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    challenge_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # DEPOSIT: 월 목표액(선택, NULL이면 순입금>0만 충족) / TARGET_VALUE: 목표 평가금액
    target_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    # RETURN_PCT: 목표 수익률(%)
    target_pct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    # DEPOSIT: 연속 적립 목표 개월수(NULL이면 오픈엔드 습관형 — 진행률 표시 없이 스트릭만)
    target_months: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 범위. NULL이면 전체 투자자산. DEPOSIT만 특정 계좌 지정 허용
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_accounts.id", ondelete="SET NULL"), nullable=True
    )

    start_month: Mapped[str] = mapped_column(String(7), nullable=False)  # "YYYY-MM"
    deadline_month: Mapped[str | None] = mapped_column(String(7), nullable=True)

    reminder_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default=CHALLENGE_ACTIVE)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("idx_investment_challenges_user_status", "user_id", "status"),)
