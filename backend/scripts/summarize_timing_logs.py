"""운영 로그에서 요청·단계 소요 시간을 요약한다(plans/151 배치 0 — 배치마다 전후 비교용).

Render 대시보드 Logs에서 복사한 텍스트(또는 `render logs` 출력)를 파일로 저장해 넘긴다:

    uv run python scripts/summarize_timing_logs.py render.log
    uv run python scripts/summarize_timing_logs.py render.log --path /api/v1/dashboard --event portfolio_overview_timing

- `http_request` 줄은 라우트 경로별 건수·p50·p95·최대 `duration_ms`와 평균 `db_queries`.
- `*_timing` 줄(대시보드·overview·총자산·할 일·이탈·목표 추천·환전 계획)은 이벤트별 `total_ms`·단계 `*_ms` p50·p95.
- `--by-request`: request_id별로 한 요청 안에서 몇 번 계산됐는지(같은 함수가 중복 호출되는지) 센다.

structlog ConsoleRenderer 형식(`... [info     ] 이벤트  key=value ...`)과 색상 코드가 섞인 줄을 모두 읽는다.
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_EVENT = re.compile(r"\[\s*\w+\s*\]\s+(\S+)")
_KV = re.compile(r"(\w+)=('[^']*'|\"[^\"]*\"|\S+)")
# 경로 안의 UUID·숫자 id를 묶어 같은 라우트끼리 합친다
_PATH_ID = re.compile(r"/(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+)(?=/|$)")


def parse_line(line: str) -> tuple[str, dict[str, str]] | None:
    clean = _ANSI.sub("", line)
    m = _EVENT.search(clean)
    if not m:
        return None
    fields = {k: v.strip("'\"") for k, v in _KV.findall(clean[m.end() :])}
    return m.group(1), fields


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    return statistics.quantiles(ordered, n=100, method="inclusive")[round(q * 100) - 1]


def _row(label: str, values: list[float], extra: str = "") -> str:
    return (
        f"{label:<55} n={len(values):>4}  p50={_pct(values, 0.5):>7.0f}  p95={_pct(values, 0.95):>7.0f}"
        f"  max={max(values):>7.0f}{extra}"
    )


@dataclass
class _Collected:
    durations: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    queries: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    timings: dict[str, dict[str, list[float]]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(list)))
    per_request: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))


def _collect_request(c: _Collected, fields: dict[str, str], path_filter: str | None) -> None:
    path = _PATH_ID.sub("/{id}", fields.get("path", "?"))
    ms = _num(fields.get("duration_ms"))
    if (path_filter and path_filter not in path) or ms is None:
        return
    c.durations[path].append(ms)
    q = _num(fields.get("db_queries"))
    if q is not None:
        c.queries[path].append(q)


def _collect_timing(c: _Collected, event: str, fields: dict[str, str]) -> None:
    for key, value in fields.items():
        n = _num(value)
        if n is not None and (key.endswith("_ms") or key in ("ms", "db_queries")):
            c.timings[event][key].append(n)
    if "request_id" in fields:
        c.per_request[fields["request_id"]][event] += 1


def _collect(lines: Iterable[str], path_filter: str | None, event_filter: str | None) -> _Collected:
    c = _Collected()
    for line in lines:
        parsed = parse_line(line)
        if parsed is None:
            continue
        event, fields = parsed
        if event == "http_request":
            _collect_request(c, fields, path_filter)
        elif event.endswith("_timing") and (not event_filter or event == event_filter):
            _collect_timing(c, event, fields)
    return c


def _render_requests(c: _Collected) -> list[str]:
    out = ["== http_request (duration_ms) =="]
    for path, values in sorted(c.durations.items(), key=lambda kv: -_pct(kv[1], 0.5)):
        q = c.queries.get(path)
        extra = f"  db_queries avg={statistics.fmean(q):.1f}" if q else ""
        out.append(_row(path, values, extra))
    return out


def _render_timings(c: _Collected) -> list[str]:
    out = ["", "== *_timing (ms) =="]
    for event, keys in sorted(c.timings.items()):
        for key, values in sorted(keys.items(), key=lambda kv: kv[0] != "total_ms"):
            out.append(_row(f"{event}.{key}", values))
    return out


def _render_repeated(c: _Collected) -> list[str]:
    repeated: Counter[str] = Counter()
    for counts in c.per_request.values():
        repeated.update(event for event, n in counts.items() if n > 1)
    out = ["", f"== 한 요청에서 2번 이상 돈 계산 (요청 {len(c.per_request)}건 중) =="]
    out.extend(f"{event:<55} {n}건" for event, n in repeated.most_common())
    if not repeated:
        out.append("없음")
    return out


def summarize(lines: Iterable[str], path_filter: str | None, event_filter: str | None, by_request: bool) -> str:
    c = _collect(lines, path_filter, event_filter)
    out: list[str] = []
    if c.durations:
        out.extend(_render_requests(c))
    if c.timings:
        out.extend(_render_timings(c))
    if by_request and c.per_request:
        out.extend(_render_repeated(c))
    return "\n".join(out) if out else "일치하는 로그 줄이 없습니다"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("log_file", help="로그 파일 경로('-'면 표준입력)")
    parser.add_argument("--path", help="http_request 경로 부분 문자열 필터")
    parser.add_argument("--event", help="*_timing 이벤트 이름 필터")
    parser.add_argument("--by-request", action="store_true", help="request_id별 중복 계산 횟수")
    args = parser.parse_args()
    if args.log_file == "-":
        lines: Iterable[str] = sys.stdin
    else:
        lines = Path(args.log_file).read_text(encoding="utf-8", errors="replace").splitlines()
    print(summarize(lines, args.path, args.event, args.by_request))


if __name__ == "__main__":
    main()
