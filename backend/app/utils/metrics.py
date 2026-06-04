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
