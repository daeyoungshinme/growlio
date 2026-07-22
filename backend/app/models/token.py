import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class KisToken(Base):
    """KIS OAuth2 액세스 토큰 (DB 영속화 — 캐시 미스 시 fallback)

    account_id가 있으면 계좌별 토큰, 없으면 유저 레벨 토큰.
    unique 제약은 migration에서 partial index로 처리:
      - account_id IS NULL  → (user_id, is_mock_mode) unique
      - account_id IS NOT NULL → (account_id) unique
    """

    __tablename__ = "kis_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_accounts.id", ondelete="CASCADE"), nullable=True
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(String(50), default="Bearer", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_mock_mode: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "uq_kis_token_account",
            "account_id",
            unique=True,
            postgresql_where="account_id IS NOT NULL",
        ),
        Index(
            "uq_kis_token_user_mode",
            "user_id",
            "is_mock_mode",
            unique=True,
            postgresql_where="account_id IS NULL",
        ),
    )


class KiwoomToken(Base):
    """키움 OpenAPI+ OAuth2 액세스 토큰 (DB 영속화 — 캐시 미스 시 fallback)

    키움은 전역 자격증명 없음 — account_id는 항상 NOT NULL.
    unique 제약: uq_kiwoom_token_account (account_id)
    """

    __tablename__ = "kiwoom_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_accounts.id", ondelete="CASCADE"), nullable=False
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(String(50), default="Bearer", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_mock_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("uq_kiwoom_token_account", "account_id", unique=True),)
