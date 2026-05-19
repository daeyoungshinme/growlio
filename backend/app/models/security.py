import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Security(Base):
    """종목 마스터 데이터"""

    __tablename__ = "securities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    # KOSPI | KOSDAQ | NYSE | NASDAQ | AMEX
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    name_ko: Mapped[str | None] = mapped_column(String(200))
    name_en: Mapped[str | None] = mapped_column(String(200))
    # KRW | USD
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    is_etf: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("ticker", "market", name="uq_security_ticker_market"),
        Index("idx_securities_ticker", "ticker"),
        Index("idx_securities_market", "market"),
    )
