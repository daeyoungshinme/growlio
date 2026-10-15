"""app/limiter.py rate_limit_key — 프록시 뒤에서 사용자/클라이언트별 버킷이 분리되는지."""

from __future__ import annotations

import base64
import json

from starlette.requests import Request

from app.limiter import rate_limit_key


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
