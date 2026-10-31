"""pykrx 호출 공용 진입점 — 프로세스 전역 락 + import 시 출력 억제."""

from __future__ import annotations

import contextlib
import io
import threading
from collections.abc import Iterator
from types import ModuleType

_pykrx_lock = threading.Lock()
"""pykrx는 동시(멀티스레드) 호출에 안전하지 않아 프로세스 크래시가 관측됐다 — 여러 조합/종목이
run_in_executor로 동시에 pykrx를 호출할 수 있는 모든 경로(목표 역산 기간별 추천, 배당 수집 등)에서
이 락으로 호출을 완전히 직렬화한다. threading.Lock을 쓰는 이유: 호출부는 실행기 워커 스레드에서 도는
동기 함수이므로 asyncio.Lock/Semaphore가 아니라 스레드 락이 맞다."""


@contextlib.contextmanager
def quiet_pykrx() -> Iterator[ModuleType]:
    """락을 잡은 채 `pykrx.stock`을 넘긴다. pykrx 호출은 반드시 이 블록 안에서 한다.

    pykrx import 시 출력되는 "KRX 로그인 실패" 메시지는 억제한다(익명 폴백으로 기능은 정상).
    """
    with _pykrx_lock:
        with contextlib.redirect_stdout(io.StringIO()):
            from pykrx import stock
        yield stock
