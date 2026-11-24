"""scripts/summarize_timing_logs.py — 실제 ConsoleRenderer 출력 형식을 읽는지(plans/151 배치 0)."""

import importlib.util
import sys
from pathlib import Path

import structlog

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "summarize_timing_logs.py"
_spec = importlib.util.spec_from_file_location("summarize_timing_logs", _SCRIPT)
assert _spec
assert _spec.loader
summarize_timing_logs = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = summarize_timing_logs  # dataclass가 정의 모듈을 sys.modules에서 찾는다
_spec.loader.exec_module(summarize_timing_logs)


def _render(event: str, colors: bool = False, **fields) -> str:
    renderer = structlog.dev.ConsoleRenderer(colors=colors)
    return renderer(None, "info", {"event": event, "level": "info", "timestamp": "2026-11-24T00:00:00Z", **fields})


def test_parse_console_line_with_and_without_colors():
    for colors in (False, True):
        parsed = summarize_timing_logs.parse_line(
            _render("http_request", colors=colors, path="/api/v1/dashboard", duration_ms=120, db_queries=9)
        )
        assert parsed is not None
        event, fields = parsed
        assert event == "http_request"
        assert fields["path"] == "/api/v1/dashboard"
        assert fields["duration_ms"] == "120"
        assert fields["db_queries"] == "9"


def test_summarize_groups_ids_and_counts_repeated_calls():
    lines = [
        _render("http_request", path="/api/v1/tactical/0b9f7f3e-2f43-4c1e-9a55-1c2d3e4f5a6b", duration_ms=100),
        _render("http_request", path="/api/v1/tactical/1b9f7f3e-2f43-4c1e-9a55-1c2d3e4f5a6b", duration_ms=300),
        _render("portfolio_overview_timing", request_id="r1", total_ms=40, db_queries=4),
        _render("portfolio_overview_timing", request_id="r1", total_ms=60, db_queries=4),
        _render("asset_totals_timing", request_id="r2", total_ms=10),
        "random noise line",
    ]
    out = summarize_timing_logs.summarize(lines, None, None, by_request=True)
    assert "/api/v1/tactical/{id}" in out
    assert "n=   2" in out
    assert "portfolio_overview_timing.total_ms" in out
    assert "portfolio_overview_timing" in out.split("2번 이상")[1]
    assert "asset_totals_timing" not in out.split("2번 이상")[1]
