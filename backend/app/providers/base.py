"""금융 데이터 제공자 추상 인터페이스."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.asset import AssetAccount


@dataclass
class Position:
    ticker: str
    name: str
    market: str
    qty: int
    avg_price: float  # 항상 KRW
    current_price: float  # 항상 KRW
    currency: str  # KRW | USD (원본 통화)
    value_krw: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    avg_price_usd: float | None = None  # 해외 종목 원본 USD 평단가 (표시용)
    usd_rate: float | None = None  # 평단가 환산에 사용한 환율 (표시용)


@dataclass
class BalanceResult:
    positions: list[Position] = field(default_factory=list)
    total_value_krw: float = 0.0
    deposit_krw: float = 0.0  # 예수금 (KRW)
    deposit_foreign: float = 0.0  # 해외 예수금 (원화 환산 전)
    invested_krw: float = 0.0  # 매입금액
    pnl_krw: float = 0.0  # 평가손익
    usd_krw_rate: float = field(default_factory=lambda: settings.usd_krw_fallback_rate)
    extra: dict[str, Any] = field(default_factory=dict)


def raw_krw_to_position(p: dict[str, Any]) -> Position:
    """원화(KRW) 원본 포지션 dict를 Position으로 변환하는 공용 헬퍼.

    KIS/Kiwoom 모두 원화 종목 변환 로직이 거의 동일했던 것을 공용화한 것.
    해외(USD) 종목 변환은 브로커별로 환율 처리 방식이 달라 각 provider에 남겨둔다.
    """
    qty = int(p.get("qty", 0))
    current_price = float(p.get("current_price", 0))
    return Position(
        ticker=p["ticker"],
        name=p["name"],
        market=p["market"],
        qty=qty,
        avg_price=float(p.get("avg_price", 0)),
        current_price=current_price,
        currency="KRW",
        value_krw=float(p.get("value_krw", 0)) or current_price * qty,
    )


class BrokerProvider(ABC):
    """증권사 동기화 공통 인터페이스.

    구현체는 SyncError 계층 예외만 raise해야 한다. 증권사별 내부 예외는 내부에서 변환.
    """

    PROVIDER_ID: str = ""
    PROVIDER_NAME: str = ""

    @abstractmethod
    async def sync(
        self,
        account: AssetAccount,
        db: AsyncSession,
        redis: aioredis.Redis | None,
    ) -> BalanceResult:
        """잔고·보유종목을 조회해 BalanceResult를 반환한다."""
