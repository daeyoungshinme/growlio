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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.core.database import Base


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
    # 이 알림 행 자체의 스코프. portfolio.alert_scope와 동기화되지만 별도 컬럼으로 저장한다 —
    # account_id는 AGGREGATE 스코프에서도 AUTO 모드면 NOT NULL이 되므로(아래 참고),
    # account_id의 NULL 여부로는 이 행이 AGGREGATE인지 PER_ACCOUNT인지 판별할 수 없다.
    alert_scope: Mapped[str] = mapped_column(String(20), nullable=False, default="AGGREGATE")
    # portfolio.alert_scope == AGGREGATE: AUTO 모드 실행 계좌(매수 주문 대상, 분석은 연결 계좌 전체 합산).
    # portfolio.alert_scope == PER_ACCOUNT: 분석 스코프 + AUTO 실행 계좌(동일 계좌, 이 행이 그 계좌 전용).
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_accounts.id", ondelete="SET NULL"), nullable=True
    )
    # 주문 유형: MARKET | LIMIT
    order_type: Mapped[str] = mapped_column(String(10), nullable=False, default="MARKET")
    # 시장 신호 연동 모드: DISABLED | CAUTIOUS(RED 시 건너뜀) | STRICT(YELLOW|RED 시 건너뜀)
    market_condition_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="DISABLED")
    # AUTO 모드 실행 시각 (HH:MM KST, 예: "09:30"), None이면 장 중 최초 5분 tick에 실행
    auto_execution_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # NOTIFY 모드 알림 발송 시각 (HH:MM KST, 기본: "08:30")
    notify_time: Mapped[str] = mapped_column(String(5), nullable=False, server_default="08:30")
    # AUTO 모드 매수 주문 대기시간(분) — 플랜 이메일 발송 후 이 시간 뒤 자동 실행(그 사이 취소 가능).
    # 매도는 대기시간이 아닌 이메일 승인 필요(당일 장마감 미응답 시 자동 만료).
    buy_wait_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    # 세금영향 게이트: DISABLED(기본) | ENABLED — 켜져 있으면 매도로 인한 추정 양도세가
    # max_tax_impact_krw를 초과할 때 AUTO 플랜 생성을 건너뛴다. market_condition_mode와 대칭 설계.
    tax_impact_gate_mode: Mapped[str] = mapped_column(String(10), nullable=False, server_default="DISABLED")
    max_tax_impact_krw: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # plain UniqueConstraint는 NULL을 서로 다른 값으로 취급해 중복을 막지 못하므로,
        # AGGREGATE / PER_ACCOUNT를 alert_scope 컬럼 기준 partial unique index로 분리해 보호한다.
        Index(
            "uq_rebalancing_alert_aggregate",
            "user_id",
            "portfolio_id",
            unique=True,
            postgresql_where=text("alert_scope = 'AGGREGATE'"),
        ),
        Index(
            "uq_rebalancing_alert_per_account",
            "user_id",
            "portfolio_id",
            "account_id",
            unique=True,
            postgresql_where=text("alert_scope = 'PER_ACCOUNT'"),
        ),
        Index("idx_rebalancing_alerts_user_active", "user_id", "is_active"),
        # 10분/5분 간격 스케줄 job(check_rebalancing_alerts/_run_auto_execution)은 user_id
        # 조건 없이 전체 활성 알림을 스캔하므로, user_id가 선두인 위 인덱스로는 서빙되지 않는다.
        Index("idx_rebalancing_alerts_active_mode", "is_active", "mode"),
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
