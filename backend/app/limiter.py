import base64
import json

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

# Supabase access token payload는 1KB 안팎 — 그보다 훨씬 큰 값은 디코드하지 않는다
_MAX_PAYLOAD_LEN = 4096


def _jwt_subject(authorization: str) -> str | None:
    """Bearer JWT의 `sub`를 서명 검증 없이 꺼낸다 — 버킷 구분용일 뿐 인증이 아니다.

    서명을 보지 않으므로 아무 `sub`나 만들어 넣을 수 있다. 그래서 인증이 필요한 라우트에서만 의미가
    있고(위조 토큰은 401), 인증 없는 라우트는 `ip_rate_limit_key`로 고정해야 한도를 우회당하지 않는다.
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token.count(".") != 2:
        return None
    payload = token.split(".")[1]
    if len(payload) > _MAX_PAYLOAD_LEN:
        return None
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, UnicodeDecodeError, RecursionError):
        # 깊게 중첩된 JSON은 RecursionError — 키 계산에서 500을 내지 않는다
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
    return ip_rate_limit_key(request)


def ip_rate_limit_key(request: Request) -> str:
    """클라이언트 IP 버킷 — 인증 없는 라우트용. 위조 JWT `sub`로 버킷을 바꿔 한도를 우회하지 못하게 한다.

    남은 한계: 데코레이터 없는 인증 라우트의 기본 한도(120/min)는 SlowAPIMiddleware가 인증 전에 키를
    계산하므로, 피해자의 사용자 UUID를 아는 사람이 위조 토큰으로 그 버킷을 소진시킬 수 있다. UUID는
    외부에 노출되지 않고 결과가 일시적 429뿐이라 서명 검증(JWKS, 비동기) 비용 대신 감수한다.
    """
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return f"ip:{forwarded or get_remote_address(request)}"


# in-memory storage — 단일 인스턴스(Render free plan) 배포라 인스턴스 간 rate limit 공유가 불필요.
# Redis-backed storage는 요청마다 Redis 커맨드를 소모해 Upstash 월간 한도를 빠르게 소진시켰다.
# default_limits는 @limiter.limit() 데코레이터가 없는 라우트에 대한 안전망 — 데코레이터가 있는
# 라우트는 그 값만 적용되고 default_limits와 합산되지 않음(slowapi override_defaults 동작).
limiter = Limiter(key_func=rate_limit_key, default_limits=["120/minute"])
