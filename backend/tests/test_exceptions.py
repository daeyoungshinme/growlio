"""앱 예외 클래스 단위 테스트."""

from __future__ import annotations


def test_provider_api_error_stores_detail_and_http_status():
    from app.exceptions import ProviderApiError

    err = ProviderApiError("API 오류", http_status=422)

    assert err.detail == "API 오류"
    assert err.http_status == 422
    assert str(err) == "API 오류"


def test_provider_api_error_default_http_status():
    from app.exceptions import ProviderApiError

    err = ProviderApiError("기본 오류")

    assert err.http_status == 400
