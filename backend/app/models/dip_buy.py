"""낙폭 추매 안내 플랜 — 적립과 별도로 둔 여윳돈을 지수 낙폭 구간별 비율로 나눠 추매를 안내한다(plans/147).

주문은 하지 않는다. 사용자가 직접 사고 "추매했어요"로 기록하면 그 구간을 완료로 두고 여윳돈에서 뺀다.
지수가 고점 근처로 회복하면 완료 기록을 지우고 다음 하락 사이클을 시작한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DipBuyPlan(Base):
    __tablename__ = "dca_dip_buy_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    index_ticker: Mapped[str] = mapped_column(String(8), nullable=False, default="QQQ", server_default="QQQ")
    # 남은 여윳돈(원). 추매 완료 시 차감, 사용자가 언제든 고칠 수 있다
    reserve_krw: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0, server_default="0")
    # [{"drawdown_pct": 10, "ratio_pct": 20}, …] — 낙폭 오름차순
    tiers: Mapped[list] = mapped_column(JSONB, nullable=False)
    # 이번 사이클 첫 추매 때의 여윳돈 — 추매로 잔액이 줄어도 구간 비율의 기준액이 흔들리지 않게 고정
    cycle_base_krw: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    # [{"tier": 0, "amount_krw": 2000000, "done_at": "2026-11-23T…"}]
    completed: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("portfolio_id", name="uq_dca_dip_buy_plans_portfolio"),
        Index("idx_dca_dip_buy_plans_user", "user_id"),
    )
