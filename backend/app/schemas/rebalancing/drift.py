"""드리프트 요약 스키마 (대시보드용 경량 조회)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class PortfolioDriftSummary(BaseModel):
    portfolio_id: uuid.UUID
    portfolio_name: str
    needs_rebalancing: bool
    threshold_pct: float  # 알림 임계값 (없으면 기본값 5.0)
    relative_threshold_pct: float | None = None  # 상대 이탈 기준(목표 대비 %) — None이면 끔(plans/136)
    max_drift_pct: float  # 이탈 종목 중 최대 |weight_diff_pct|
    drifted_items_count: int  # 이탈 판정(filter_drifting_items)에 걸린 종목 수
    has_composite_signal: bool = False  # drift는 없지만 리스크/시장 신호로 점검을 권장하는 경우
    composite_reason: str | None = None  # has_composite_signal=True일 때 사유 문구
    has_alert_configured: bool = False  # 활성 RebalancingAlert 설정 여부 (없으면 이 포트폴리오는 알림이 발송되지 않음)

    # ── 시점 판단(plans/136) — 진단 탭 행 표시용, 계산 실패 시 기본값 ──
    timing: Literal["NOW", "SPLIT", "HOLD", "WATCH", "OK"] | None = None
    timing_reason: str | None = None
    last_rebalanced_at: datetime | None = None  # 주문이 한 건이라도 성공한 마지막 실행
    next_scheduled_date: date | None = None  # 스케줄 알림(SCHEDULE_ONLY·BOTH)의 다음 실행·발송일(KST)
    schedule_type: str | None = None  # next_scheduled_date를 정한 알림의 주기(MONTHLY 등)
    estimated_trade_krw: float = 0.0  # 지금 이탈 항목을 맞출 때 매도 금액 추정
    estimated_cost_krw: float = 0.0  # 수수료 + 해외 양도세 추정(참고용)
    estimated_overseas_gain_krw: float = 0.0  # 해외 매도 실현손익 추정(과세이연 계좌 제외)
