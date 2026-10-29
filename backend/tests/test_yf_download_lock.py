"""yahoo_price.yf_download — yfinance 배치 다운로드 직렬화 (plans/79 G)."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app.services.market_data.yahoo_price import yf_download


def test_concurrent_downloads_never_overlap():
    # yfinance download는 전역 shared._DFS를 쓰므로 두 호출이 겹치면 결과가 섞인다 — 래퍼가 막아야 한다
    active = 0
    max_active = 0
    guard = threading.Lock()

    def fake_download(tickers, **kwargs):
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        with guard:
            active -= 1
        return tickers

    with patch("yfinance.download", side_effect=fake_download), ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda s: yf_download([s], progress=False), ["A", "B", "C", "D"]))

    assert max_active == 1
    assert results == [["A"], ["B"], ["C"], ["D"]]
