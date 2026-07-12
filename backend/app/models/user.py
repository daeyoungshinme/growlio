import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.asset import AssetAccount


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    needs_password_reset: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    settings: Mapped["UserSettings"] = relationship(back_populates="user", uselist=False, passive_deletes=True)
    asset_accounts: Mapped[list["AssetAccount"]] = relationship(back_populates="user", passive_deletes=True)


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # 투자 목표
    goal_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    goal_annual_return_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    goal_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    goal_initial_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    annual_deposit_goal: Mapped[float | None] = mapped_column(Numeric(18, 2))
    monthly_deposit_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    retirement_target_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annual_dividend_goal: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    # 목표 역산 추천 엔진에 병합할 사용자 등록 후보 ETF (RECOMMENDATION_UNIVERSE 외 추가분, 최대 10개)
    goal_candidate_tickers: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    # 목표 역산 추천 엔진 파라미터 (사용자 조정 가능, NULL이면 기존 하드코딩 기본값 사용 — 하위호환)
    goal_risk_tolerance: Mapped[str | None] = mapped_column(String(20), nullable=True)
    goal_max_weight_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    goal_cagr_lookback_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # DART OpenAPI 자격증명 (AES-256 암호화)
    dart_api_key: Mapped[str | None] = mapped_column(String(512))
    # 알림 설정
    notification_email: Mapped[str | None] = mapped_column(String(255))
    monthly_report_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # drift가 없어도 리스크 집중/시장 위험 신호가 있으면 추가로 발송 — 신호 자체가 유저 단위이므로 계정 단일 설정
    composite_signal_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fcm_token: Mapped[str | None] = mapped_column(String(512))
    # 자동 DCA (정기매수)
    auto_dca_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_dca_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_dca_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    auto_dca_portfolio_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    auto_dca_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    auto_dca_last_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="settings")
