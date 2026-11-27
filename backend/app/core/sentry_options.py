"""Sentry `data_collection` 설정 — `main.py`의 `sentry_sdk.init`이 쓴다.

sentry-sdk 3.0에서 send_default_pii·include_local_variables가 `data_collection`으로 통합됐고 항목별 기본값이
"수집"이다. 2.x의 send_default_pii=False 의미를 항목별로 명시해 끈다. 키 이름은 SDK 메이저마다 바뀔 수 있어
`tests/test_sentry_options.py`가 SDK가 이 값을 실제로 받아들이는지 확인한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentry_sdk._types import DataCollectionUserOptions

SENTRY_DATA_COLLECTION: DataCollectionUserOptions = {
    "user_info": False,
    "cookies": {"mode": "off"},
    # 요청 본문에 브로커 앱키·시크릿(계좌 연동)이 실린다
    "http_bodies": [],
    "database_query_data": False,
    # 스택 지역변수에 복호화된 브로커 자격증명이 있을 수 있다 — report_handled_failure와 같은 이유
    "stack_frame_variables": False,
    # KIS 잔고·주문 GET은 계좌번호를 쿼리스트링(CANO·ACNT_PRDT_CD)에 싣는다. 기본 denylist는 이 이름을 거르지
    # 않아 httpx breadcrumb(모든 이벤트에 붙음)·span의 URL에 그대로 남는다(plans/157 A1). 진단에 쓰는 쿼리값이 없다
    "url_query_params": {"mode": "off"},
}
