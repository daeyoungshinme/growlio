"""요청 단위 DB 계측 — 한 요청이 쿼리를 몇 번·몇 ms 보냈는지 `http_request` 로그에 싣는다(plans/151 배치 0).

SQLAlchemy async는 드라이버 greenlet에 호출 쪽 contextvars 컨텍스트를 넘겨 주므로(`gr_context`) cursor 이벤트에서
현재 요청의 카운터를 찾을 수 있다. `asyncio.gather`·`create_task`로 갈라진 작업도 컨텍스트를 복사하므로 같은 카운터
객체에 더해진다. 요청 밖(스케줄러 잡·기동 예열)은 카운터가 없어 아무것도 하지 않는다.
"""

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass
class RequestMetrics:
    db_queries: int = 0
    db_ms: float = 0.0


_current: ContextVar[RequestMetrics | None] = ContextVar("request_metrics", default=None)


def start_request_metrics() -> tuple[RequestMetrics, Token[RequestMetrics | None]]:
    metrics = RequestMetrics()
    return metrics, _current.set(metrics)


def reset_request_metrics(token: Token[RequestMetrics | None]) -> None:
    _current.reset(token)


def record_db_query(elapsed_ms: float) -> None:
    metrics = _current.get()
    if metrics is not None:
        metrics.db_queries += 1
        metrics.db_ms += elapsed_ms


def current_db_queries() -> int | None:
    """지금까지 이 요청이 보낸 쿼리 수 — 요청 밖이면 None."""
    metrics = _current.get()
    return metrics.db_queries if metrics is not None else None
