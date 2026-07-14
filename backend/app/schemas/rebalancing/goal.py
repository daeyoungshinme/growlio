"""목표 역산 추천 및 복합신호 배너 스키마."""

from pydantic import BaseModel


class GoalRecommendationItem(BaseModel):
    ticker: str
    name: str
    market: str
    weight: float  # 0~100


class GoalRecommendation(BaseModel):
    """목표 역산 추천 — 로드맵 A 3단계. 자동 반영되지 않으며 사용자가 확인 후 수동 적용한다."""

    generated_at: str  # ISO timestamp
    is_configured: bool  # 목표금액/목표연도 미설정 시 False
    required_return_pct: float | None = None  # 목표 달성에 필요한 연평균 수익률(%)
    required_dividend_yield_pct: float | None = None  # 목표 배당 달성에 필요한 배당수익률(%, 현재 자산 기준)
    recommended_items: list[GoalRecommendationItem] = []
    expected_return_pct: float | None = None  # 추천 비중의 가중평균 CAGR(%) — cagr_lookback_years 기간 기준
    expected_dividend_yield_pct: float | None = None  # 추천 비중의 가중평균 배당수익률(%)
    note: str | None = None  # 미설정/이미 달성/달성 불가/리스크 성향 클램프 등 상태 설명
    cagr_lookback_years: int = 10  # 기대수익률(CAGR) 산출 기간(년) — 진단화면 10년 고정 지표와 다를 수 있음
    risk_tolerance: str = "CONSERVATIVE"  # 적용된 리스크 성향 (CONSERVATIVE/BALANCED/AGGRESSIVE)
    max_weight_pct: float = 40.0  # 적용된 종목당 최대 비중(%)


class HorizonGoalRecommendation(BaseModel):
    """투자기간(단기/중기/장기) × 세제유형 조합 기반 추천 — 목표 역산이 아닌 기간별 리스크 성향 +
    세제유형별 투자 가능 시장(국내/해외)을 반영한 재배분.

    태그된 계좌가 없는 (기간, 세제유형) 조합은 응답 목록에서 아예 생략된다(카드 자체에서 숨김 처리).
    """

    investment_horizon: str  # SHORT_TERM | MID_TERM | LONG_TERM
    tax_type: str  # GENERAL | ISA | PENSION_SAVINGS | IRP | OVERSEAS_DEDICATED
    base_krw: float  # 해당 (기간, 세제유형) 조합에 태그된 계좌들의 자산총액
    account_count: int
    recommended_items: list[GoalRecommendationItem] = []
    expected_return_pct: float | None = None
    risk_tolerance: str  # 기간별로 고정 적용됨 (단기=CONSERVATIVE/중기=BALANCED/장기=AGGRESSIVE)
    max_weight_pct: float
    # recommended_items에 현금성 자산(CMA·파킹통장) 합성 항목이 포함돼 있는지(SHORT_TERM 전용).
    # True면 실제 매수 가능한 티커가 아니므로 프론트에서 포트폴리오 "적용" 버튼을 숨겨야 한다.
    includes_cash_equivalent: bool = False
    note: str | None = None


class HorizonRecommendationResponse(BaseModel):
    generated_at: str  # ISO timestamp
    recommendations: list[HorizonGoalRecommendation] = []


class CompositeSignalStatus(BaseModel):
    """진단탭 상단 복합신호(시장/리스크) 배너 — 유저 단위 단일 신호."""

    enabled: bool  # UserSettings.composite_signal_alerts_enabled
    triggered: bool  # enabled=True이고 조건(시장 RED 또는 리스크 이상) 충족 시 True
    reason: str | None = None
    has_active_alert: bool  # 활성 리밸런싱 알림이 1개라도 있는지 (없으면 enabled=True여도 실제 발송 안 됨)
