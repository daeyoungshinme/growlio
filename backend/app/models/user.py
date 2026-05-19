import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    settings: Mapped["UserSettings"] = relationship(back_populates="user", uselist=False)
    asset_accounts: Mapped[list["AssetAccount"]] = relationship(back_populates="user")  # type: ignore[name-defined]


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
    # KIS 자격증명 (AES-256 암호화)
    kis_app_key: Mapped[str | None] = mapped_column(String(512))
    kis_app_secret: Mapped[str | None] = mapped_column(String(512))
    kis_account_no: Mapped[str | None] = mapped_column(String(20))
    kis_is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    # DART OpenAPI 자격증명 (AES-256 암호화)
    dart_api_key: Mapped[str | None] = mapped_column(String(512))
    # 오픈뱅킹
    ob_access_token: Mapped[str | None] = mapped_column(String)
    ob_refresh_token: Mapped[str | None] = mapped_column(String)
    ob_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ob_user_seq_no: Mapped[str | None] = mapped_column(String(20))
    # 알림 설정
    notification_email: Mapped[str | None] = mapped_column(String(255))

    user: Mapped["User"] = relationship(back_populates="settings")
