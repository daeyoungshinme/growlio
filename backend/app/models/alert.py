import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.database import Base


class _AlertMixin:
    """공통 알림 컬럼 — ExchangeRateAlert, RebalancingAlert, StockPriceAlert에서 사용."""

    @declared_attr
    def id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    @declared_attr
    def is_active(cls) -> Mapped[bool]:
        return mapped_column(Boolean, default=True, nullable=False)

    @declared_attr
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ExchangeRateAlert(_AlertMixin, Base):
    __tablename__ = "exchange_rate_alerts"

    target_rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    direction: Mapped[str] = mapped_column(Enum("BELOW", "ABOVE", name="alert_direction_enum"), nullable=False)
    max_trigger_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_exchange_rate_alerts_user", "user_id"),)


class RebalancingAlert(_AlertMixin, Base):
    __tablename__ = "rebalancing_alerts"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    threshold_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(12), nullable=False, default="DAILY")
    schedule_day_of_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule_day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 발동 조건: DRIFT_ONLY(드리프트), SCHEDULE_ONLY(스케줄 날 항상), BOTH(스케줄+비스케줄 드리프트)
    trigger_condition: Mapped[str] = mapped_column(String(20), nullable=False, default="DRIFT_ONLY")
    # 실행 모드: NOTIFY(이메일 알림만) | AUTO(자동 주문 실행)
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="NOTIFY")
    # 자동 실행 전략: BUY_ONLY | FULL
    strategy: Mapped[str] = mapped_column(String(20), nullable=False, default="BUY_ONLY")
    # AUTO 모드 실행 계좌 (KIS/키움)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_accounts.id", ondelete="SET NULL"), nullable=True
    )
    # 주문 유형: MARKET | LIMIT
    order_type: Mapped[str] = mapped_column(String(10), nullable=False, default="MARKET")
    # 시장 신호 연동 모드: DISABLED | CAUTIOUS(RED 시 건너뜀) | STRICT(YELLOW|RED 시 건너뜀)
    market_condition_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="DISABLED")
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ── 예수금 입금 감지 트리거 ──────────────────────────────────────
    deposit_trigger_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deposit_trigger_min_amount_krw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_deposit_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deposit_accounts: Mapped[list["RebalancingAlertDepositAccount"]] = relationship(
        "RebalancingAlertDepositAccount", cascade="all, delete-orphan", lazy="selectin"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "portfolio_id", name="uq_rebalancing_alert_user_portfolio"),
        Index("idx_rebalancing_alerts_user_active", "user_id", "is_active"),
    )


class StockPriceAlert(_AlertMixin, Base):
    __tablename__ = "stock_price_alerts"

    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    target_price: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    direction: Mapped[str] = mapped_column(Enum("BELOW", "ABOVE", name="stock_alert_direction_enum"), nullable=False)
    max_trigger_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_stock_price_alerts_user_active", "user_id", "is_active"),
        Index("idx_stock_price_alerts_ticker", "ticker"),
    )


class RebalancingAlertDepositAccount(Base):
    """예수금 입금 감지 대상 계좌 — RebalancingAlert 당 복수 선택 가능."""

    __tablename__ = "rebalancing_alert_deposit_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rebalancing_alerts.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_accounts.id", ondelete="CASCADE"), nullable=False
    )
    last_known_deposit_krw: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)

    __table_args__ = (
        UniqueConstraint("alert_id", "account_id", name="uq_alert_deposit_account"),
        Index("idx_alert_deposit_accounts_alert", "alert_id"),
    )


class AlertHistory(Base):
    """알림 발송 이력 — 환율/리밸런싱/주가 알림 발송 시 자동 저장."""

    __tablename__ = "alert_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # EXCHANGE_RATE | REBALANCING | STOCK_PRICE
    alert_type: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("idx_alert_history_user_created", "user_id", "created_at"),)
