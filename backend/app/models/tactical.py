"""전술 배분 전략 — 매크로 신호 + 차트 추세로 국면을 판정해 QQQ/SPY/현금 목표 비중을 제안한다.

자동 주문은 하지 않는다. 국면 전환 시 알림만 보내고, 사용자가 제안 비중을 포트폴리오 목표에 적용한 뒤
기존 리밸런싱 실행(진단 → 2단계 확인 → 주문) 화면에서 직접 실행한다.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TacticalStrategy(Base):
    """포트폴리오당 1개. 국면 확정 상태(last_regime)와 확정 대기 상태(pending_*)를 저장한다."""

    __tablename__ = "tactical_strategies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # 국면 전환 알림 수신 여부(전략 자체는 항상 조회 가능)
    notify_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # {"RISK_ON": {"QQQ": 50, "SPY": 40, "CASH": 10}, ...} — NULL이면 기본 비중표 사용
    regime_weights: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 확정 국면 — 같은 새 국면이 서로 다른 KST 날짜에 2번 관측돼야 바뀐다(하루 노이즈로 인한 왕복 방지)
    last_regime: Mapped[str | None] = mapped_column(String(12), nullable=True)
    last_regime_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_regime: Mapped[str | None] = mapped_column(String(12), nullable=True)
    pending_first_seen: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 마지막으로 포트폴리오 목표 비중에 적용한 국면(알림/배지에서 "아직 미적용" 판정용)
    applied_regime: Mapped[str | None] = mapped_column(String(12), nullable=True)
    # 마지막으로 전환 알림을 보낸(또는 알릴 필요 없다고 처리한) 확정 국면. 앱 조회 시에도 국면이 확정될 수 있어
    # "advance가 True를 돌려줬을 때만 알림"으로 하면 조회가 알림을 가로챈다 — last_regime과 비교해 판정한다.
    notified_regime: Mapped[str | None] = mapped_column(String(12), nullable=True)

    # 나스닥/S&P 틸트(tactical_tilt) — 주식 몫 안에서 QQQ↔SPY로 옮길 %p(0이면 끔). 월 1회 갱신이라 확정 대기 없이
    # 그 달 첫 점검일의 판정을 그대로 쓴다.
    tilt_shift_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default="0")
    last_tilt: Mapped[str | None] = mapped_column(String(12), nullable=True)
    tilt_evaluated_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    # 눌림목(웅덩이) 현금 투입(tactical_dip) — 현금에서 주식으로 옮길 최대 %p(0이면 끔). 투입 단계(0~3)는 한 웅덩이
    # 안에서 올라가기만 하고, 회복·방어 국면이면 0. notified_dip_level은 단계 상승 알림 중복 방지용.
    dip_shift_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default="0")
    dip_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    notified_dip_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")

    # False면 매크로 신호를 무시하고 차트 추세(SPY·QQQ 200일선)만으로 국면을 판정한다(plans/70)
    use_macro: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # 분할 적용(fraction<1) 진행 중인 국면·적용일 — 같은 국면에서 "절반 먼저"가 두 번 눌려 75%가 되는 것을 막고
    # 화면에 "나머지 적용"을 띄운다. 전체 적용·확정 국면 변경 시 비운다.
    partial_regime: Mapped[str | None] = mapped_column(String(12), nullable=True)
    partial_applied_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
