"""app/limiter.py rate_limit_key — 프록시 뒤에서 사용자/클라이언트별 버킷이 분리되는지."""

from __future__ import annotations

import base64
import json

from starlette.requests import Request

from app.limiter import ip_rate_limit_key, rate_limit_key


def _request(headers: dict[str, str], client_host: str = "10.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client_host, 1234),
    }
    return Request(scope)


def _jwt(claims: dict) -> str:
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'HS256'})}.{b64(claims)}.sig"


def test_authenticated_requests_from_same_proxy_get_separate_buckets():
    a = rate_limit_key(_request({"Authorization": f"Bearer {_jwt({'sub': 'user-a'})}"}))
    b = rate_limit_key(_request({"Authorization": f"Bearer {_jwt({'sub': 'user-b'})}"}))

    assert a == "user:user-a"
    assert b == "user:user-b"


def test_anonymous_uses_first_forwarded_hop_not_proxy_address():
    key = rate_limit_key(_request({"X-Forwarded-For": "203.0.113.7, 10.1.1.1"}, client_host="10.0.0.1"))

    assert key == "ip:203.0.113.7"


def test_falls_back_to_client_host_without_headers():
    assert rate_limit_key(_request({})) == "ip:10.0.0.1"


def test_malformed_bearer_falls_back_to_ip():
    assert rate_limit_key(_request({"Authorization": "Bearer not-a-jwt"})) == "ip:10.0.0.1"
    assert rate_limit_key(_request({"Authorization": "Bearer a.!!!.c"})) == "ip:10.0.0.1"


def test_deeply_nested_payload_falls_back_to_ip_without_raising():
    nested = base64.urlsafe_b64encode(b"[" * 3000).decode().rstrip("=")
    assert rate_limit_key(_request({"Authorization": f"Bearer h.{nested}.s"})) == "ip:10.0.0.1"


def test_oversized_payload_is_not_decoded():
    big = base64.urlsafe_b64encode(json.dumps({"sub": "x", "pad": "a" * 5000}).encode()).decode().rstrip("=")
    assert rate_limit_key(_request({"Authorization": f"Bearer h.{big}.s"})) == "ip:10.0.0.1"


def test_ip_key_ignores_forged_subject():
    # 인증 없는 라우트는 위조 sub로 버킷을 바꿀 수 없어야 한다
    headers = {"Authorization": f"Bearer {_jwt({'sub': 'forged'})}", "X-Forwarded-For": "203.0.113.7"}
    assert ip_rate_limit_key(_request(headers)) == "ip:203.0.113.7"


def test_public_routes_use_ip_key():
    from app.main import app

    public = {
        "find_account",
        "preview_plan_action",
        "cancel_buy_by_token",
        "decide_sell_by_token",
        "search_stocks",
        "get_index_region",
        "get_exchange_rate",
    }
    limits = app.state.limiter._route_limits
    found = {name.rsplit(".", 1)[-1]: lims for name, lims in limits.items() if name.rsplit(".", 1)[-1] in public}
    assert set(found) == public
    for name, lims in found.items():
        assert all(lim.key_func is ip_rate_limit_key for lim in lims), name
