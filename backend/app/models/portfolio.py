import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Portfolio(Base):
    """백테스팅·리밸런싱 공용 포트폴리오 설정."""

    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # [{ticker, name, market, weight}] — weight 합계 = 100
    # 현금: ticker="CASH", market="KRW" / 부동산: ticker="REAL_ESTATE", market="KR_PROPERTY"
    items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # STOCK_ONLY | TOTAL_ASSETS — 리밸런싱 기준 자산 (백테스팅에서는 무시)
    base_type: Mapped[str] = mapped_column(String(20), nullable=False, default="STOCK_ONLY")
    # 리밸런싱 분석 대상 계좌 UUID 목록. null이면 모든 활성 주식 계좌 사용
    account_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_portfolios_user", "user_id"),
    )
