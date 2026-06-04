"""배당금 서비스 — 하위 호환 re-export.

실제 구현:
  - app.services.dividend.calculator  (순수 계산 로직)
  - app.services.dividend.orchestrator (DB·Redis·fetch 조율)
"""

from app.services.dividend.orchestrator import (
    delete_ticker_settings,
    get_position_dividend_yields,
    get_ticker_dividend_summary,
    get_ticker_settings,
    upsert_ticker_settings,
)
from app.services.dividend_constants import KNOWN_DIVIDEND_SCHEDULES as KNOWN_DIVIDEND_SCHEDULES

__all__ = [
    "get_ticker_dividend_summary",
    "get_position_dividend_yields",
    "get_ticker_settings",
    "upsert_ticker_settings",
    "delete_ticker_settings",
    "KNOWN_DIVIDEND_SCHEDULES",
]
