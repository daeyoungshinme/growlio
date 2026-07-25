"""목표 역산 추천 및 복합신호 배너 스키마."""

from pydantic import BaseModel


class GoalRecommendationItem(BaseModel):
    ticker: str
    name: str
    market: str
    weight: float  # 0~100
    # 실시간 조회된 종목별 배당수익률(%) — 배당 목표 제약은 포트폴리오 전체 가중평균에만 걸리므로,
    # 저배당 종목도 분산 목적으로 포함될 수 있다는 걸 화면에서 구분할 수 있게 노출한다.
    # 조회 실패/데이터 없음이면 None.
    dividend_yield_pct: float | None = None


class SuggestedGoalCandidate(BaseModel):
    """등록된 후보만으로 배당 목표를 달성할 수 없을 때 제안되는 미등록 고배당 후보 — 아직
    `UserSettings.goal_candidate_tickers`에 저장되지 않았으며, 사용자가 추천 카드의 "후보에
    추가" 버튼으로 승인해야만 `PUT /settings/goal-candidate-tickers`를 통해 저장된다."""

    ticker: str
    name: str
    market: str
    asset_class: str = "EQUITY"
    dividend_yield_pct: float | None = None


class GoalRecommendation(BaseModel):
    """목표 역산 추천 — 로드맵 A 3단계. 자동 반영되지 않으며 사용자가 확인 후 수동 적용한다."""

    generated_at: str  # ISO timestamp
    is_configured: bool  # 목표금액/목표연도 미설정 시 False
    required_return_pct: float | None = None  # 목표 달성에 필요한 연평균 수익률(%)
    required_dividend_yield_pct: float | None = None  # 목표 배당 달성에 필요한 배당수익률(%, 현재 자산 기준)
    recommended_items: list[GoalRecommendationItem] = []
    expected_return_pct: float | None = None  # 추천 비중의 가중평균 CAGR(%) — cagr_lookback_years 기간 기준
    expected_dividend_yield_pct: float | None = None  # 추천 비중의 가중평균 배당수익률(%)
    expected_volatility_pct: float | None = None  # 추천 비중의 연율화 변동성(%, 공분산 기반)
    note: str | None = None  # 미설정/이미 달성/달성 불가/리스크 성향 클램프 등 상태 설명
    cagr_lookback_years: int = 10  # 기대수익률(CAGR) 산출 기간(년) — 진단화면 10년 고정 지표와 다를 수 있음
    risk_tolerance: str = "CONSERVATIVE"  # 적용된 리스크 성향 (CONSERVATIVE/BALANCED/AGGRESSIVE)
    max_weight_pct: float = 40.0  # 적용된 종목당 최대 비중(%)
    market_signal_level: str | None = None  # GREEN|YELLOW|RED — 추천 비중 계산에 반영된 시장 위험 신호 등급
    age_bracket: str | None = None  # 연령대별 추천(get_age_based_recommendation) 전용 — 적용된 나이 구간 라벨
    # recommended_items에 현금성 자산(CMA·파킹통장) 합성 항목이 포함돼 있는지(연령대별 추천 전용,
    # HorizonGoalRecommendation.includes_cash_equivalent와 동일 의미). True면 실제 매수 가능한
    # 티커가 아니므로 프론트에서 포트폴리오 "적용" 버튼을 숨겨야 한다.
    includes_cash_equivalent: bool = False
    # 등록된 후보만으로는 배당 목표를 달성할 수 없을 때 제안되는 미등록 고배당 후보 —
    # 사용자가 승인(추천 카드의 "후보에 추가" 버튼)하기 전까지는 비중 계산에 반영되지 않는다.
    suggested_candidates: list[SuggestedGoalCandidate] = []
    # 배당 목표 대비 판정 상태 — "unreachable"(등록후보로 달성 불가) | "improvable"(달성했지만
    # 더 나은 후보 존재) | "optimal"(달성했고 더 나은 후보 없음) | None(배당목표 미설정).
    # suggested_candidates가 비어 있어도 unreachable/optimal을 구분해 문구를 다르게 보여줄 수 있다.
    dividend_goal_status: str | None = None


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
    expected_dividend_yield_pct: float | None = None  # 추천 비중의 가중평균 배당수익률(%)
    expected_volatility_pct: float | None = None  # 추천 비중의 연율화 변동성(%, 공분산 기반)
    risk_tolerance: str  # 기간별로 고정 적용됨 (단기=CONSERVATIVE/중기=BALANCED/장기=AGGRESSIVE)
    max_weight_pct: float
    # recommended_items에 현금성 자산(CMA·파킹통장) 합성 항목이 포함돼 있는지(SHORT_TERM 전용).
    # True면 실제 매수 가능한 티커가 아니므로 프론트에서 포트폴리오 "적용" 버튼을 숨겨야 한다.
    includes_cash_equivalent: bool = False
    market_signal_level: str | None = None  # GREEN|YELLOW|RED — 추천 비중 계산에 반영된 시장 위험 신호 등급
    note: str | None = None
    # 등록된 후보만으로는 배당 목표를 달성할 수 없을 때 제안되는 미등록 고배당 후보 —
    # 사용자가 승인(추천 카드의 "후보에 추가" 버튼)하기 전까지는 비중 계산에 반영되지 않는다.
    suggested_candidates: list[SuggestedGoalCandidate] = []
    dividend_goal_status: str | None = None  # GoalRecommendation.dividend_goal_status와 동일 의미


class HorizonRecommendationResponse(BaseModel):
    generated_at: str  # ISO timestamp
    recommendations: list[HorizonGoalRecommendation] = []


class PortfolioExpectedMetrics(BaseModel):
    """포트폴리오의 현재 목표 비중(`Portfolio.items`)에 대한 기대수익률/배당수익률/변동성 —
    "적용 전 비교 미리보기"에서 추천 비중의 같은 지표와 나란히 보여주기 위한 값. 시세 데이터가
    없는 종목은 계산에서 제외되므로, 전 종목이 미확인이면 전부 None."""

    expected_return_pct: float | None = None
    expected_dividend_yield_pct: float | None = None
    expected_volatility_pct: float | None = None


class CompositeSignalStatus(BaseModel):
    """진단탭 상단 복합신호(시장/리스크) 배너 — 유저 단위 단일 신호."""

    enabled: bool  # UserSettings.composite_signal_alerts_enabled
    triggered: bool  # enabled=True이고 조건(시장 RED 또는 리스크 이상) 충족 시 True
    reason: str | None = None
