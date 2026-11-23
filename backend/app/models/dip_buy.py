"""낙폭 추매 안내 — 적립과 별도로 둔 여윳돈을 지수 낙폭 구간별로 나눠 추매를 안내한다(plans/147·148).

주문은 하지 않는다. 여윳돈은 사용자당 하나(`DipBuySettings`)이고 포트폴리오와 무관하다. 지수별 규칙
(`DipBuyRule`)이 여윳돈의 배분 비율을 나눠 갖고, 구간 비율은 그 몫 안에서 적용한다. 사용자가 직접 사고
"추매했어요"로 기록하면 그 구간을 완료로 두고 여윳돈에서 뺀다. 지수가 고점 근처로 회복하면 그 규칙의 완료
기록을 지우고 다음 하락 사이클을 시작한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, SmallInteger, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DipBuySettings(Base):
    """사용자당 1행 — 남은 여윳돈과 알림 방식."""

    __tablename__ = "dip_buy_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # 남은 여윳돈(원). 추매 완료 시 차감, 사용자가 언제든 고칠 수 있다
    reserve_krw: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0, server_default="0")
    # ON_REACH: 구간 도달 다음 날 아침 / MONTHLY_DAY: 매달 notify_day(휴장이면 다음 거래일)
    notify_mode: Mapped[str] = mapped_column(String(12), nullable=False, default="ON_REACH", server_default="ON_REACH")
    notify_day: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("user_id", name="uq_dip_buy_settings_user"),)


class DipBuyRule(Base):
    """지수별 추매 규칙 — 사용자당 지수 하나에 하나."""

    __tablename__ = "dip_buy_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    index_ticker: Mapped[str] = mapped_column(String(8), nullable=False)
    # 여윳돈 중 이 규칙의 몫(%) — 사용자 규칙 합계 100 이하
    allocation_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    # [{"drawdown_pct": 10, "ratio_pct": 20}, …] — 낙폭 오름차순, 비율은 이 규칙 몫 기준
    tiers: Mapped[list] = mapped_column(JSONB, nullable=False)
    # 이번 사이클 첫 추매 때의 규칙 몫 — 추매로 여윳돈이 줄어도 구간 금액이 흔들리지 않게 고정
    cycle_base_krw: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    # [{"tier": 0, "amount_krw": 2000000, "done_at": "2026-11-23T…"}]
    completed: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # 구간 도달 알림(ON_REACH)을 이미 보낸 구간 번호 — 사이클 초기화 때 함께 비운다
    notified_tiers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "index_ticker", name="uq_dip_buy_rules_user_index"),
        Index("idx_dip_buy_rules_user", "user_id"),
    )
