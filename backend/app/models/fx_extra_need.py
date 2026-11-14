"""추가 환전 항목 — 여행·해외 결제처럼 적립과 별개로 특정 날짜까지 필요한 달러(plans/123).

적립 환전 계획과 따로 계산한다 — 증권 계좌 보유 달러로 상쇄하지 않는다(보통 은행·트래블카드로 따로 바꾼다).
증권 계좌 달러 예수금으로 바꿔 두면 `reserved_account_id`로 그 계좌를 지정해, 적립 계획 보유 달러에서 뺀다.
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
    # 이 달러를 둔 증권 계좌(선택) — 지정하면 필요일 전까지 적립 환전 계획의 그 계좌 보유 달러에서
    # `exchanged_usd`만큼 뺀다. 총자산·리밸런싱·자동매수 가용 현금은 바꾸지 않는다(plans/123 후속)
    reserved_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_accounts.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_fx_extra_needs_user", "user_id"),
        Index("idx_fx_extra_needs_reserved_account", "reserved_account_id"),
    )
