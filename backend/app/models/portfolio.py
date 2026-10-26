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
    UniqueConstraint,
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
    # 지수 그룹 항목(plans/74) — 값이 있으면 이 행은 그룹 하나이고 ticker/market은 대표 매수 종목.
    # 이탈은 대표 종목+멤버 합계로 판정하고 주문은 group_expansion이 종목 단위로 전개한다
    group_key: Mapped[str | None] = mapped_column(String(64))
    group_label: Mapped[str | None] = mapped_column(String(50))

    portfolio: Mapped["Portfolio"] = relationship(back_populates="items")
    # items를 읽는 곳(selectinload(Portfolio.items))이 많아 멤버는 항상 함께 읽는다
    members: Mapped[list["PortfolioItemMember"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PortfolioItemMember.sort_order",
    )

    __table_args__ = (Index("idx_portfolio_items_portfolio", "portfolio_id"),)

    @property
    def group(self) -> dict | None:
        """응답 스키마(`PortfolioItem.group`)용 — 대표 종목은 members에 포함하지 않는다."""
        if not self.group_key:
            return None
        alt = next((m for m in self.members if m.role == GROUP_ROLE_DOMESTIC_ALT), None)
        return {
            "key": self.group_key,
            "label": self.group_label or "",
            "members": [
                {"ticker": m.ticker, "market": m.market, "name": m.name, "leverage": float(m.leverage or 1)}
                for m in self.members
                if m.role == GROUP_ROLE_MEMBER
            ],
            "domestic_alt": {"ticker": alt.ticker, "market": alt.market, "name": alt.name} if alt else None,
        }


GROUP_ROLE_MEMBER = "MEMBER"
GROUP_ROLE_DOMESTIC_ALT = "DOMESTIC_ALT"


class PortfolioItemMember(Base):
    """지수 그룹 항목의 멤버 종목 — 대표 종목 외에 같은 그룹으로 합산할 보유 종목과 국내 대체 매수 종목."""

    __tablename__ = "portfolio_item_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolio_items.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # MEMBER(합산 대상) | DOMESTIC_ALT(ISA·연금 계좌 매수용 국내 상장 대체 종목 — 합산 대상이기도 함)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=GROUP_ROLE_MEMBER)
    # 정방향 레버리지 배수 — 그룹 현재 비중은 평가액 × 배수(노출 기준)로 합산한다(QLD=2)
    leverage: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False, default=1.0, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    item: Mapped[PortfolioItem] = relationship(back_populates="members")

    __table_args__ = (
        UniqueConstraint("portfolio_item_id", "ticker", "market", name="uq_portfolio_item_members_key"),
        Index("idx_portfolio_item_members_item", "portfolio_item_id"),
    )


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
