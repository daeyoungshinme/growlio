"""alert_history.alert_type 길이 회귀 테스트 (plans/61 A1).

String(20)일 때 "YEAR_END_TAX_REMINDER"(21자) 이력 저장이 매번 실패했다. 앱 코드에서 이력 저장 경로로
넘기는 alert_type 문자열 리터럴을 AST로 모아 컬럼 길이를 넘지 않는지 고정한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.models.alert import ALERT_TYPE_MAX_LEN, AlertHistory

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# 이력 저장 함수 → alert_type 위치 인자 인덱스
_POSITIONAL = {
    "save_alert_history": 2,
    "apply_alert_trigger": 2,
    "notify_and_record_trigger": 2,
}
_KEYWORDS = {"alert_type", "history_alert_type"}


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _collect_alert_types() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            candidates: list[ast.expr] = [kw.value for kw in node.keywords if kw.arg in _KEYWORDS]
            idx = _POSITIONAL.get(name or "")
            if idx is not None and len(node.args) > idx:
                candidates.append(node.args[idx])
            for value in candidates:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    found[value.value] = f"{path.relative_to(APP_DIR)}:{value.lineno}"
    return found


def test_column_length_matches_constant():
    assert AlertHistory.__table__.c.alert_type.type.length == ALERT_TYPE_MAX_LEN


def test_collector_finds_known_types():
    found = _collect_alert_types()
    # 수집기가 실제로 동작하는지(경로가 바뀌어 0건이 되면 아래 길이 테스트가 공허해진다)
    assert {"REBALANCING", "YEAR_END_TAX_REMINDER", "MARKET_SIGNAL_DIGEST"} <= found.keys()


def test_all_alert_types_fit_column():
    too_long = {t: loc for t, loc in _collect_alert_types().items() if len(t) > ALERT_TYPE_MAX_LEN}
    assert not too_long, f"alert_type이 컬럼 길이({ALERT_TYPE_MAX_LEN})를 넘는다: {too_long}"
