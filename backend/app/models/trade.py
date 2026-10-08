"""수기 매매 기록 — 기간별 매수 종목·수익률 계산 전용.

브로커 sync는 체결내역을 가져오지 않으므로(잔고·보유종목만) 기간별 매수분은 기본적으로 일별 스냅샷
포지션 비교로 추정한다. 사용자가 이 테이블에 매수/매도를 직접 기록하면 해당 (계좌, 종목)은 추정 대신
기록 값으로 정확히 계산된다(`services/period_purchase_service.py`).

`Transaction`(현금흐름: 입출금·배당·이자)과 의도적으로 분리 — BUY/SELL을 섞으면 유형 필터가 없는
입출금 집계가 오염된다. 보유 포지션(Position)은 이 기록으로 자동 수정하지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TradeRecord(Base):
    """사용자가 직접 입력한 매수/매도 1건."""

    __tablename__ = "trade_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_accounts.id", ondelete="SET NULL"), nullable=True
    )
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # BUY | SELL (TradeSide)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    qty: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    price_krw: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)  # 항상 KRW (해외는 프론트 환산)
    fee: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_trade_records_user_date", "user_id", "trade_date"),
        Index("idx_trade_records_account_ticker_date", "account_id", "ticker", "market", "trade_date"),
    )
