"""Sentry data_collection 설정이 SDK에 그대로 받아들여지고 계좌번호·자격증명을 거르는지 (plans/157 A1)."""

from __future__ import annotations

import sentry_sdk
from sentry_sdk.data_collection import _apply_data_collection_filtering_to_query_string

from app.core.sentry_options import SENTRY_DATA_COLLECTION

_DUMMY_DSN = "https://key@o0.ingest.sentry.io/0"
_KIS_QUERY = "CANO=12345678&ACNT_PRDT_CD=01&OVRS_EXCG_CD=NASD"


def _resolved() -> dict:
    return sentry_sdk.Client(dsn=_DUMMY_DSN, data_collection=SENTRY_DATA_COLLECTION).options["data_collection"]


def test_sdk_accepts_every_key_as_given():
    # SDK 메이저에서 키 이름이 바뀌면 조용히 기본값(수집)으로 돌아간다 — 우리가 준 값이 그대로 풀렸는지 본다
    resolved = _resolved()
    for key, value in SENTRY_DATA_COLLECTION.items():
        assert resolved[key] == value, key


def test_kis_account_number_query_is_dropped():
    assert (
        _apply_data_collection_filtering_to_query_string(
            query_string=_KIS_QUERY, behaviour=_resolved()["url_query_params"]
        )
        is None
    )


def test_sdk_default_would_leak_account_number():
    # 기본 denylist가 CANO를 거르지 않는다는 전제 — SDK가 거르기 시작하면 이 설정의 이유를 다시 본다
    default = sentry_sdk.Client(dsn=_DUMMY_DSN).options["data_collection"]["url_query_params"]
    filtered = _apply_data_collection_filtering_to_query_string(query_string=_KIS_QUERY, behaviour=default)
    assert filtered is not None
    assert "12345678" in filtered
