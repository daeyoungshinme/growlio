from typing import Literal

from pydantic import BaseModel

ActionItemKind = Literal["REBALANCE", "DCA_SHORTFALL", "TAX_WARNING", "TAX_ACTION", "CHALLENGE"]
ActionItemPriority = Literal["HIGH", "MEDIUM", "LOW"]


class ActionItem(BaseModel):
    """홈 "지금 할 일" 카드 1행 — 여러 도메인의 행동 신호를 같은 모양으로 맞춘다(docs/plans/50 M5)."""

    id: str  # 프론트 key·dedup용 안정 식별자 (예: "rebalance:<portfolio_id>")
    kind: ActionItemKind
    priority: ActionItemPriority
    title: str
    detail: str
    cta_label: str
    link: str
    deadline: str | None = None  # YYYY-MM-DD
