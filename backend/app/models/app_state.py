from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppState(Base):
    """재시작에도 유지되어야 하는 소규모 key-value 상태 (구 Redis durable state 대체).

    시장신호 등급전환 감지 마지막 값, 알림 중복발송 방지 dedup 플래그 등
    콜드스타트 후에도 값이 남아있어야 정확성이 보장되는 상태 전용.
    """

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
