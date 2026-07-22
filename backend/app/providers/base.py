"""금융 데이터 제공자 추상 인터페이스."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.cache_store import CacheStore
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


def raw_usd_to_position(p: dict[str, Any], usd_krw_rate: float) -> Position:
    """USD 원본 해외 포지션 dict를 KRW 환산 Position으로 변환하는 공용 헬퍼.

    avg_price/current_price는 KRW로 환산해 저장하되, avg_price_usd/usd_rate에
    원본 USD 값과 환산에 사용한 환율을 표시용으로 보존한다. KIS/Kiwoom 공용.
    """
    avg_usd = float(p.get("avg_price", 0))
    cur_usd = float(p.get("current_price", 0))
    qty = int(p.get("qty", 0))
    return Position(
        ticker=p["ticker"],
        name=p["name"],
        market=p["market"],
        qty=qty,
        avg_price=avg_usd * usd_krw_rate,
        current_price=cur_usd * usd_krw_rate,
        currency="USD",
        value_krw=float(p.get("value_krw", cur_usd * usd_krw_rate * qty)),
        avg_price_usd=avg_usd,
        usd_rate=usd_krw_rate,
    )


def raw_to_position(p: dict[str, Any], usd_krw_rate: float) -> Position:
    """원본 포지션 dict(KRW/USD)를 Position으로 변환하는 공용 진입점.

    ticker/market을 정규화(strip+upper)한다 — 수동입력(schemas/asset.py의
    ManualPosition.ticker_not_empty)과 동일한 규칙. 브로커 원본 응답은 이 정규화가
    없으면(특히 키움처럼 고정폭 필드를 쓰는 API) 트레일링 공백이 섞여 들어와
    position_aggregator.py의 "{ticker}-{market}" 매칭 키가 수동입력/타 계좌 포지션과
    어긋난다.

    p["currency"]로 KRW/USD를 분기해 raw_krw_to_position/raw_usd_to_position을 호출한다.
    """
    p = {**p, "ticker": str(p["ticker"]).strip().upper(), "market": str(p["market"]).strip().upper()}
    if p.get("currency") == "USD":
        return raw_usd_to_position(p, usd_krw_rate)
    return raw_krw_to_position(p)


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
        cache: CacheStore | None,
    ) -> BalanceResult:
        """잔고·보유종목을 조회해 BalanceResult를 반환한다."""
