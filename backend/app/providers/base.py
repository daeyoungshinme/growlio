"""금융 데이터 제공자 추상 인터페이스."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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
    avg_price: float        # 항상 KRW
    current_price: float    # 항상 KRW
    currency: str           # KRW | USD (원본 통화)
    value_krw: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    avg_price_usd: float | None = None   # 해외 종목 원본 USD 평단가 (표시용)
    usd_rate: float | None = None        # 평단가 환산에 사용한 환율 (표시용)


@dataclass
class BalanceResult:
    positions: list[Position] = field(default_factory=list)
    total_value_krw: float = 0.0
    deposit_krw: float = 0.0          # 예수금 (KRW)
    deposit_foreign: float = 0.0      # 해외 예수금 (원화 환산 전)
    invested_krw: float = 0.0         # 매입금액
    pnl_krw: float = 0.0              # 평가손익
    usd_krw_rate: float = 1300.0
    extra: dict[str, Any] = field(default_factory=dict)


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
