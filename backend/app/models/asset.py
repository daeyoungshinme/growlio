import uuid
from datetime import date, datetime

from sqlalchemy import ARRAY, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
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
    # 수동 주식 포지션 [{ticker, name, market, qty, avg_price, current_price}]
    manual_positions: Mapped[list | None] = mapped_column(JSONB)
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

    user: Mapped["User"] = relationship(back_populates="asset_accounts")  # type: ignore[name-defined]
    snapshots: Mapped[list["AssetSnapshot"]] = relationship(back_populates="account")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")

    __table_args__ = (Index("idx_asset_accounts_user_id", "user_id"),)


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
    positions: Mapped[list | None] = mapped_column(JSONB)

    # MANUAL | KIS_API | KIWOOM_API | OPEN_BANKING
    source: Mapped[str] = mapped_column(String(20), default="MANUAL", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["AssetAccount"] = relationship(back_populates="snapshots")

    __table_args__ = (
        UniqueConstraint("account_id", "snapshot_date", name="uq_snapshot_account_date"),
        Index("idx_snapshots_user_date", "user_id", "snapshot_date"),
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

    account: Mapped["AssetAccount | None"] = relationship(back_populates="transactions")

    __table_args__ = (
        Index("idx_transactions_user_date", "user_id", "transaction_date"),
        Index("idx_transactions_account", "account_id"),
    )


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
