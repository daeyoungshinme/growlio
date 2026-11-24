"""단계별 소요 시간 로그 — 어느 구간이 지연을 지배하는지 운영 로그로 확인한다(plans/66·151).

요약은 `scripts/summarize_timing_logs.py`로 낸다.
"""

import time
from typing import Any

import structlog

from app.core.request_metrics import current_db_queries

logger = structlog.get_logger()


def elapsed_ms(started: float) -> int:
    """`time.perf_counter()`로 잡은 시작점부터의 경과 ms."""
    return round((time.perf_counter() - started) * 1000)


class StepTimer:
    """`mark("x")`는 직전 mark 이후 경과를 `x_ms`로 기록하고, `log()`가 한 줄로 남긴다(`total_ms` 포함).

    요청 안에서 만들면 그동안 보낸 DB 쿼리 수를 `db_queries`로 함께 남긴다 — 요청 전체 카운터의 차이라
    같은 요청에서 동시에 도는 다른 작업의 쿼리도 섞일 수 있다.
    """

    def __init__(self, event: str, **fields: Any) -> None:
        self._event = event
        self._fields: dict[str, Any] = dict(fields)
        self._started = self._last = time.perf_counter()
        self._queries_at_start = current_db_queries()
        self.steps: dict[str, int] = {}

    def mark(self, stage: str) -> None:
        now = time.perf_counter()
        self.steps[f"{stage}_ms"] = round((now - self._last) * 1000)
        self._last = now

    def log(self, **fields: Any) -> None:
        payload: dict[str, Any] = {**self._fields, **fields, **self.steps, "total_ms": elapsed_ms(self._started)}
        queries_now = current_db_queries()
        if queries_now is not None and self._queries_at_start is not None:
            payload["db_queries"] = queries_now - self._queries_at_start
        logger.info(self._event, **payload)
