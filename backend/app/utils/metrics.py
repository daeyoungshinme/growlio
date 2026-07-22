"""Prometheus 커스텀 메트릭 정의.

애플리케이션 전역에서 import하여 사용한다.
"""

from prometheus_client import Counter, Histogram

broker_sync_duration = Histogram(
    "broker_sync_duration_seconds",
    "계좌 동기화 소요 시간 (초)",
    labelnames=["data_source", "status"],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float("inf")),
)

alert_trigger_count = Counter(
    "alert_trigger_total",
    "발송된 알림 수",
    labelnames=["alert_type"],
)

rebalancing_execution_count = Counter(
    "rebalancing_execution_total",
    "리밸런싱 실행 횟수",
    labelnames=["status"],
)

# HTTP 요청 응답시간 (라우터 prefix + HTTP method 레이블)
http_request_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP 요청 처리 시간 (초)",
    labelnames=["method", "path_prefix", "status_class"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf")),
)

# 캐시 히트/미스
cache_hit_count = Counter(
    "cache_hit_total",
    "캐시 히트 수",
    labelnames=["cache_name"],
)

cache_miss_count = Counter(
    "cache_miss_total",
    "캐시 미스 수",
    labelnames=["cache_name"],
)

# 느린 쿼리 카운터 (slow_query_ms 초과)
slow_query_count = Counter(
    "slow_query_total",
    "slow_query_ms 임계값 초과 쿼리 수",
)
