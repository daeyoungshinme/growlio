"""추가 환전 항목 — 여행·해외 결제처럼 적립과 별개로 특정 날짜까지 필요한 달러(plans/123).

적립 환전 계획과 따로 계산한다 — 증권 계좌 보유 달러로 상쇄하지 않는다(보통 은행·트래블카드로 따로 바꾼다).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FxExtraNeed(Base):
    __tablename__ = "fx_extra_needs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_usd: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    exchanged_usd: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0, server_default="0")
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (Index("idx_fx_extra_needs_user", "user_id"),)
