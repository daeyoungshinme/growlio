import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PortfolioItem(Base):
    """포트폴리오 구성 종목 — portfolios.items JSONB 대체."""

    __tablename__ = "portfolio_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="items")

    __table_args__ = (Index("idx_portfolio_items_portfolio", "portfolio_id"),)


class PortfolioAccount(Base):
    """포트폴리오 계좌 필터 — portfolios.account_ids JSONB 대체."""

    __tablename__ = "portfolio_accounts"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_accounts.id", ondelete="CASCADE"), nullable=False
    )

    portfolio: Mapped["Portfolio"] = relationship(back_populates="linked_accounts")

    __table_args__ = (PrimaryKeyConstraint("portfolio_id", "account_id"),)


class Portfolio(Base):
    """백테스팅·리밸런싱 공용 포트폴리오 설정."""

    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # STOCK_ONLY | TOTAL_ASSETS — 리밸런싱 기준 자산 (백테스팅에서는 무시)
    base_type: Mapped[str] = mapped_column(String(20), nullable=False, default="STOCK_ONLY")
    # AGGREGATE(연결 계좌 전체 합산 1개 알림) | PER_ACCOUNT(연결 계좌마다 독립 알림/AUTO 설정)
    alert_scope: Mapped[str] = mapped_column(String(20), nullable=False, server_default="AGGREGATE")
    # 명시적으로 지정된 기간/세제유형 태그 — 미지정(null)이면 기준 포트폴리오로 지정된 계좌들의
    # 태그로부터 추론(전부 동일할 때만). 목표 역산 추천(기간·세제유형별)이 어느 포트폴리오에
    # 적용될지 판별하는 데 사용
    investment_horizon: Mapped[str | None] = mapped_column(String(20))
    tax_type: Mapped[str | None] = mapped_column(String(30))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list[PortfolioItem]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
        order_by=PortfolioItem.sort_order,
    )
    linked_accounts: Mapped[list[PortfolioAccount]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("idx_portfolios_user", "user_id"),)

    @property
    def account_ids(self) -> list[str] | None:
        """하위 호환: rebalancing.py의 getattr(portfolio, 'account_ids', None) 패턴 지원."""
        if not self.linked_accounts:
            return None
        return [str(pa.account_id) for pa in self.linked_accounts]
