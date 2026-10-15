import base64
import json

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _jwt_subject(authorization: str) -> str | None:
    """Bearer JWT의 `sub`를 서명 검증 없이 꺼낸다 — 버킷 구분용일 뿐 인증이 아니다.

    위조 토큰은 어차피 인증 단계에서 401이 나므로, 위조로 버킷을 바꿔 얻는 이득은 401 응답뿐이다.
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token.count(".") != 2:
        return None
    payload = token.split(".")[1]
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, UnicodeDecodeError):
        return None
    sub = claims.get("sub") if isinstance(claims, dict) else None
    return sub if isinstance(sub, str) and sub else None


def rate_limit_key(request: Request) -> str:
    """요청 버킷 키 — 로그인 사용자는 사용자 단위, 그 외는 클라이언트 IP 단위.

    운영 요청은 Vercel rewrite → Render 프록시를 거쳐 들어오고 uvicorn은 프록시 헤더를 신뢰하지
    않으므로 `request.client.host`(get_remote_address)는 프록시 주소다. 그 값을 키로 쓰면 모든
    사용자가 한 버킷을 공유해 한 명이 `3/hour` 같은 한도를 소진시키면 전원이 막힌다.
    비로그인 요청의 `X-Forwarded-For` 첫 hop은 클라이언트가 위조할 수 있지만, 그 경우 얻는 것은
    자기 한도 우회뿐이고(공용 버킷보다 낫다) 로그인 엔드포인트는 사용자 키를 쓴다.
    """
    sub = _jwt_subject(request.headers.get("authorization", ""))
    if sub:
        return f"user:{sub}"
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return f"ip:{forwarded or get_remote_address(request)}"


# in-memory storage — 단일 인스턴스(Render free plan) 배포라 인스턴스 간 rate limit 공유가 불필요.
# Redis-backed storage는 요청마다 Redis 커맨드를 소모해 Upstash 월간 한도를 빠르게 소진시켰다.
# default_limits는 @limiter.limit() 데코레이터가 없는 라우트에 대한 안전망 — 데코레이터가 있는
# 라우트는 그 값만 적용되고 default_limits와 합산되지 않음(slowapi override_defaults 동작).
limiter = Limiter(key_func=rate_limit_key, default_limits=["120/minute"])
