import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

VALID_MARKETS: frozenset[str] = frozenset({"KOSPI", "KOSDAQ", "NYSE", "NASDAQ", "AMEX", "OTHER"})





class AssetAccount(Base):
    """자산 계좌 마스터 — 수동/KIS API/오픈뱅킹 계좌를 통합 관리"""

    __tablename__ = "asset_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # BANK_ACCOUNT | DEPOSIT | STOCK_KIS | STOCK_KIWOOM | STOCK_OTHER | CASH_OTHER | OTHER | REAL_ESTATE
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # MANUAL | KIS_API | KIWOOM_API | OPEN_BANKING
    data_source: Mapped[str] = mapped_column(String(20), nullable=False, default="MANUAL")
    institution: Mapped[str | None] = mapped_column(String(100))

    # 오픈뱅킹 연결 정보
    ob_bank_code: Mapped[str | None] = mapped_column(String(10))
    ob_account_no_encrypted: Mapped[str | None] = mapped_column(String(200))
    ob_fintech_use_no: Mapped[str | None] = mapped_column(String(50), unique=True)

    # KIS 계좌 (STOCK_KIS)
    kis_account_no: Mapped[str | None] = mapped_column(String(20))
    # 계좌별 KIS 자격증명 (AES-256 암호화) — 없으면 UserSettings 전역 자격증명 사용
    kis_app_key: Mapped[str | None] = mapped_column(String(512))
    kis_app_secret: Mapped[str | None] = mapped_column(String(512))
    is_mock_mode: Mapped[bool] = mapped_column(Boolean, default=True)

    # 키움 계좌 (STOCK_KIWOOM) — data_source=KIWOOM_API
    kiwoom_account_no: Mapped[str | None] = mapped_column(String(20))
    # 계좌별 키움 자격증명 (AES-256 암호화) — 전역 폴백 없음, 항상 필수
    kiwoom_app_key: Mapped[str | None] = mapped_column(String(512))
    kiwoom_app_secret: Mapped[str | None] = mapped_column(String(512))

    # 수동 입력 금액 / 종목 목록
    manual_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    manual_currency: Mapped[str] = mapped_column(String(3), default="KRW")
    manual_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 예수금 (현금 잔고) — KIS sync 시 자동 갱신, 수동 계좌는 사용자 직접 입력
    deposit_krw: Mapped[float | None] = mapped_column(Numeric(18, 2))
    # 외화 예수금 (USD) — KIS 해외 계좌 sync 시 자동 갱신, 수동 계좌는 사용자 직접 입력
    deposit_usd: Mapped[float | None] = mapped_column(Numeric(18, 4))
    # 부동산 상세 (REAL_ESTATE 전용) — {address, property_type, purchase_price_krw, purchase_date, mortgage_balance_krw}
    real_estate_details: Mapped[dict | None] = mapped_column(JSONB)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_in_total: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    target_portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="asset_accounts")  # type: ignore[name-defined]  # noqa: F821
    snapshots: Mapped[list["AssetSnapshot"]] = relationship(back_populates="account")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")
    current_positions: Mapped[list["Position"]] = relationship(
        back_populates="account",
        primaryjoin="and_(Position.account_id==AssetAccount.id, Position.snapshot_id==None)",
        cascade="all, delete-orphan",
        viewonly=False,
    )

    __table_args__ = (
        Index("idx_asset_accounts_user_active", "user_id", "is_active"),
        Index("idx_asset_accounts_user_active_include", "user_id", "is_active", "include_in_total"),
        Index("idx_asset_accounts_user_active_type", "user_id", "is_active", "asset_type"),
        Index("idx_asset_accounts_data_source", "user_id", "data_source"),
    )


class AssetSnapshot(Base):
    """일별 자산 스냅샷 — 추이 차트 및 수익률 계산용"""

    __tablename__ = "asset_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_accounts.id", ondelete="SET NULL")
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_krw: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    amount_original: Mapped[float | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KRW", nullable=False)
    usd_krw_rate: Mapped[float | None] = mapped_column(Numeric(10, 4))

    # 주식 계좌 상세
    invested_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    unrealized_pnl: Mapped[float | None] = mapped_column(Numeric(18, 2))

    # MANUAL | KIS_API | KIWOOM_API | OPEN_BANKING
    source: Mapped[str] = mapped_column(String(20), default="MANUAL", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["AssetAccount"] = relationship(back_populates="snapshots")
    position_items: Mapped[list["Position"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("account_id", "snapshot_date", name="uq_snapshot_account_date"),
        Index("idx_snapshots_user_date", "user_id", "snapshot_date"),
        Index("idx_snapshots_user_id", "user_id"),
        Index("idx_asset_snapshots_account_date", "account_id", "snapshot_date"),
        Index(
            "idx_snapshots_account_date_desc",
            "account_id", "snapshot_date",
            postgresql_ops={"snapshot_date": "DESC"},
        ),
        Index(
            "idx_asset_snapshots_user_account_date",
            "user_id", "account_id", "snapshot_date",
            postgresql_ops={"snapshot_date": "DESC"},
        ),
    )


class Transaction(Base):
    """입출금 및 배당금 내역."""

    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_accounts.id", ondelete="SET NULL"), nullable=True
    )
    # DEPOSIT | WITHDRAWAL | DIVIDEND
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    fee: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)

    account: Mapped["AssetAccount | None"] = relationship(back_populates="transactions")

    __table_args__ = (
        Index("idx_transactions_user_date", "user_id", "transaction_date"),
        Index("idx_transactions_account", "account_id"),
        Index("idx_transactions_user_type", "user_id", "transaction_type"),
        Index("idx_transactions_user_type_date", "user_id", "transaction_type", "transaction_date"),
        Index("idx_transactions_account_type_date", "account_id", "transaction_type", "transaction_date"),
        Index(
            "uq_div_account_ticker_date",
            "account_id", "ticker", "transaction_date",
            unique=True,
            postgresql_where=text(
                "transaction_type = 'DIVIDEND' AND account_id IS NOT NULL AND ticker IS NOT NULL"
            ),
        ),
    )


class RebalancingExecution(Base):
    """리밸런싱 실행 이력 — 수동/자동/원클릭 실행 결과를 저장한다."""

    __tablename__ = "rebalancing_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True
    )
    # MANUAL | AUTO | ONE_CLICK
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False, default="MANUAL")
    # FULL | BUY_ONLY
    strategy: Mapped[str] = mapped_column(String(20), nullable=False, default="FULL")
    total_success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_fail: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    result_items: Mapped[list["RebalancingExecutionResult"]] = relationship(
        back_populates="execution",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("idx_rebalancing_executions_user", "user_id", "executed_at"),)


class RebalancingExecutionResult(Base):
    """리밸런싱 실행 결과 — 계좌/주문 단위 결과 저장 (rebalancing_executions.results JSONB 대체)."""

    __tablename__ = "rebalancing_execution_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rebalancing_executions.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[str | None] = mapped_column(String(50))
    account_name: Mapped[str | None] = mapped_column(String(200))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY | SELL | SKIPPED
    ticker: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(200))
    market: Mapped[str | None] = mapped_column(String(20))
    quantity: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # SUCCESS | FAILED | SKIPPED
    order_no: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False, default="MARKET")

    execution: Mapped["RebalancingExecution"] = relationship(back_populates="result_items")

    __table_args__ = (Index("idx_rebalancing_results_execution", "execution_id"),)


class UserTickerSettings(Base):
    """사용자별 종목 설정 — 배당월 수동 override."""

    __tablename__ = "user_ticker_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    dividend_months: Mapped[list | None] = mapped_column(ARRAY(Integer), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "ticker", "market", name="uq_user_ticker_settings"),
        Index("idx_user_ticker_settings_user", "user_id"),
    )


class Position(Base):
    """계좌 보유 포지션 — AssetAccount.manual_positions + AssetSnapshot.positions JSONB 대체.

    snapshot_id IS NULL  → 계좌 현재 포지션 (manual_positions 대체)
    snapshot_id NOT NULL → 스냅샷 시점 포지션 (snapshot.positions 대체)
    """

    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_accounts.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_snapshots.id", ondelete="CASCADE"), nullable=True
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    qty: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    avg_price: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)       # 항상 KRW
    avg_price_usd: Mapped[float | None] = mapped_column(Numeric(18, 4))            # 원본 USD 평단가 (해외)
    current_price: Mapped[float | None] = mapped_column(Numeric(18, 2))            # 항상 KRW
    value_krw: Mapped[float | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KRW", nullable=False)
    usd_rate: Mapped[float | None] = mapped_column(Numeric(10, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["AssetAccount"] = relationship(
        back_populates="current_positions",
        foreign_keys="[Position.account_id]",
    )
    snapshot: Mapped["AssetSnapshot | None"] = relationship(back_populates="position_items")

    def to_dict(self) -> dict:
        """Position → 하위 호환 dict 형식 변환 (manual_positions JSONB 형식)."""
        return {
            "ticker": self.ticker,
            "name": self.name,
            "market": self.market,
            "qty": float(self.qty),
            "avg_price": float(self.avg_price),
            "avg_price_usd": float(self.avg_price_usd) if self.avg_price_usd else None,
            "current_price": float(self.current_price) if self.current_price else None,
            "value_krw": float(self.value_krw) if self.value_krw else None,
            "currency": self.currency,
            "usd_rate": float(self.usd_rate) if self.usd_rate else None,
        }

    __table_args__ = (
        Index("idx_positions_account_snapshot", "account_id", "snapshot_id"),
        Index(
            "idx_positions_snapshot_notnull",
            "snapshot_id",
            postgresql_where=text("snapshot_id IS NOT NULL"),
        ),
        Index("idx_positions_snapshot_id", "snapshot_id"),
        Index(
            "idx_positions_account_no_snapshot",
            "account_id",
            postgresql_where=text("snapshot_id IS NULL"),
        ),
        Index("idx_positions_account_ticker", "account_id", "ticker"),
    )
