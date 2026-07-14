"""드리프트 요약 스키마 (대시보드용 경량 조회)."""

import uuid

from pydantic import BaseModel


class DriftedItem(BaseModel):
    ticker: str
    name: str
    weight_diff_pct: float  # 양수=매수 필요, 음수=매도 필요


class PortfolioDriftSummary(BaseModel):
    portfolio_id: uuid.UUID
    portfolio_name: str
    needs_rebalancing: bool
    threshold_pct: float  # 알림 임계값 (없으면 기본값 5.0)
    max_drift_pct: float  # 이탈 종목 중 최대 |weight_diff_pct|
    drifted_items_count: int  # threshold를 초과한 종목 수
    top_drifted_items: list[DriftedItem]  # 이탈 크기 상위 3개
    has_composite_signal: bool = False  # drift는 없지만 리스크/시장 신호로 점검을 권장하는 경우
    composite_reason: str | None = None  # has_composite_signal=True일 때 사유 문구
    has_alert_configured: bool = False  # 활성 RebalancingAlert 설정 여부 (없으면 이 포트폴리오는 알림이 발송되지 않음)
