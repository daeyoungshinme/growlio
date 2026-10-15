"""app/limiter.py rate_limit_key — 프록시 뒤에서 사용자/클라이언트별 버킷이 분리되는지."""

from __future__ import annotations

import base64
import json

from starlette.requests import Request

from app.limiter import ip_rate_limit_key, peer_rate_limit_key, rate_limit_key


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


def test_peer_key_uses_last_hop_which_client_cannot_forge():
    # origin 직접 호출: 클라이언트가 넣은 첫 hop은 바뀌어도 Render가 붙인 마지막 hop은 같다
    a = peer_rate_limit_key(_request({"X-Forwarded-For": "1.1.1.1, 198.51.100.9"}))
    b = peer_rate_limit_key(_request({"X-Forwarded-For": "2.2.2.2, 198.51.100.9"}))
    assert a == b == "peer:198.51.100.9"


def test_peer_key_falls_back_to_client_host():
    assert peer_rate_limit_key(_request({})) == "peer:10.0.0.1"
    assert peer_rate_limit_key(_request({"X-Forwarded-For": " , "})) == "peer:10.0.0.1"


def _route_limits() -> dict:
    from app.main import app

    return {name.rsplit(".", 1)[-1]: lims for name, lims in app.state.limiter._route_limits.items()}


def test_sensitive_public_routes_stack_ip_and_peer_keys():
    # 인증 없이 상태를 바꾸거나 토큰을 받는 라우트: 첫 hop IP 한도 + 위조 불가 peer 상한
    limits = _route_limits()
    for name in ("find_account", "preview_plan_action", "cancel_buy_by_token", "decide_sell_by_token"):
        key_funcs = {lim.key_func for lim in limits[name]}
        assert key_funcs == {ip_rate_limit_key, peer_rate_limit_key}, name


def test_low_value_lookup_routes_use_default_user_key():
    # 로그인 사용자가 주로 부르는 조회 라우트는 공용 IP 버킷을 나눠 쓰지 않는다(계획 57 B2)
    limits = _route_limits()
    for name in ("search_stocks", "get_index_region", "get_exchange_rate"):
        assert all(lim.key_func is rate_limit_key for lim in limits[name]), name


def test_forged_forwarded_for_cannot_bypass_peer_cap():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    statuses = [
        client.post(
            "/api/v1/auth/find-account",
            json={"display_name": "x"},
            headers={"X-Forwarded-For": f"203.0.113.{i}, 198.51.100.9"},
        ).status_code
        for i in range(31)
    ]
    # 첫 hop을 매번 바꿔 ip 한도(3/hour)는 피하지만 peer 상한(30/hour)에 걸린다
    assert statuses[:30] == [200] * 30
    assert statuses[30] == 429
