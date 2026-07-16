"""AUTO 리밸런싱 2단계 플랜(계획 생성 → 매수 대기/매도 승인) 데이터 모델.

기존 `RebalancingExecution`/`RebalancingExecutionResult`(실행 완료 이력)와는 별개로,
"아직 실행되지 않은 계획"의 생명주기(대기/승인/취소/만료/실행)를 추적한다.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RebalancingPlan(Base):
    """AUTO 알림 1회 발동으로 생성된 계획 — BUY/SELL leg를 묶는 헤더."""

    __tablename__ = "rebalancing_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rebalancing_alerts.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_accounts.id", ondelete="SET NULL"), nullable=True
    )
    # 플랜 생성 시점 스냅샷 — 원본 alert가 나중에 삭제/변경돼도 그대로 실행 가능하도록 값 복제
    strategy: Mapped[str] = mapped_column(String(20), nullable=False)
    order_type: Mapped[str] = mapped_column(String(10), nullable=False)
    composite_level_at_plan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    legs: Mapped[list["RebalancingPlanLeg"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_rebalancing_plans_user_created", "user_id", "created_at"),
        Index("idx_rebalancing_plans_alert", "alert_id"),
    )


class RebalancingPlanLeg(Base):
    """플랜의 매수/매도 절반 — 각자 독립된 대기/승인/실행 상태를 가진다."""

    __tablename__ = "rebalancing_plan_legs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rebalancing_plans.id", ondelete="CASCADE"), nullable=False
    )
    # BUY | SELL
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    # PENDING | EXECUTED | CANCELED | REJECTED | EXPIRED | FAILED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    # BUY: 자동 실행 예정 시각. SELL: 승인 만료(당일 장마감) 시각.
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # USER_APP | USER_EMAIL | SYSTEM_AUTO | SYSTEM_EXPIRY
    decided_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 이메일 링크용 단일 사용 토큰 — 원문은 저장하지 않고 SHA-256 해시만 저장
    action_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rebalancing_executions.id", ondelete="SET NULL"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    plan: Mapped["RebalancingPlan"] = relationship(back_populates="legs")
    items: Mapped[list["RebalancingPlanItem"]] = relationship(
        back_populates="leg",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_rebalancing_plan_legs_plan", "plan_id"),
        Index("idx_rebalancing_plan_legs_status_deadline", "status", "deadline_at"),
        Index(
            "uq_rebalancing_plan_legs_token_hash",
            "action_token_hash",
            unique=True,
            postgresql_where=text("action_token_hash IS NOT NULL"),
        ),
    )


class RebalancingPlanItem(Base):
    """leg 내 종목별 주문 라인 — 계획 생성 시점에 수량이 고정된다."""

    __tablename__ = "rebalancing_plan_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    leg_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rebalancing_plan_legs.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    market: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    order_type: Mapped[str] = mapped_column(String(10), nullable=False, default="MARKET")
    limit_price: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    reference_price: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)

    leg: Mapped["RebalancingPlanLeg"] = relationship(back_populates="items")

    __table_args__ = (Index("idx_rebalancing_plan_items_leg", "leg_id"),)
