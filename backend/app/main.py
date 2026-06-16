import re
import time
import uuid
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response

from app.api.v1.router import router
from app.config import settings
from app.database import get_db
from app.exceptions import AppError
from app.kis.client import KisApiError
from app.limiter import limiter
from app.providers.http_client import close_http_client
from app.redis_client import close_redis, get_redis
from app.scheduler import init_scheduler, scheduler
from app.utils.metrics import http_request_duration

logger = structlog.get_logger()

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.sentry_release or None,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    logger.info(
        "sentry_initialized",
        env=settings.app_env,
        release=settings.sentry_release or "unset",
    )

_SECRET_PATTERN = re.compile(
    r"(appkey|appsecret|secretkey|access_token|refresh_token|Bearer|password|Authorization"
    r"|api_key|apikey|dart_api_key|encryption_key|jwt_secret|supabase_key|redis_url|database_url)"
    r"[=:\s\"']+[A-Za-z0-9+/=_\-\.]{4,}",
    re.IGNORECASE,
)


def _sanitize(text: str) -> str:
    return _SECRET_PATTERN.sub(r"\1=[REDACTED]", text)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Redis 연결 확인 — 실패 시 즉시 종료
    try:
        redis = await get_redis()
        await redis.ping()  # type: ignore[misc]  # redis-py stub returns bool|Awaitable[bool]
        logger.info("redis_connected")
    except Exception as e:
        logger.error("redis_startup_failed", error=str(e))
        raise RuntimeError(f"Redis에 연결할 수 없습니다: {e}") from e

    if settings.app_env == "production" and not settings.metrics_token:
        logger.warning("metrics_token_unset", message="/metrics 엔드포인트가 차단됩니다. METRICS_TOKEN을 설정하세요.")

    init_scheduler()
    logger.info("app_started", env=settings.app_env)
    yield
    scheduler.shutdown()
    await close_http_client()
    await close_redis()
    logger.info("app_stopped")


app = FastAPI(
    title="Growlio — 자산관리 + 적립식 자동매매",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env == "development" else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]  # slowapi handler signature

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://static.toss.im https://ssl.pstatic.net; "
        "connect-src 'self' https://*.supabase.co wss://*.supabase.co; "
        "object-src 'none'; "
        "frame-ancestors 'none';"
    )
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _path_prefix(path: str) -> str:
    """'/api/v1/dashboard/summary' → '/api/v1/dashboard'"""
    parts = path.rstrip("/").split("/")
    return "/".join(parts[:4]) if len(parts) >= 4 else path


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    elapsed = time.monotonic() - start
    duration_ms = round(elapsed * 1000)
    request_id = getattr(request.state, "request_id", "-")
    status_class = f"{response.status_code // 100}xx"
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
        request_id=request_id,
    )
    http_request_duration.labels(
        method=request.method,
        path_prefix=_path_prefix(request.url.path),
        status_class=status_class,
    ).observe(elapsed)
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(KisApiError)
async def kis_api_error_handler(request: Request, exc: KisApiError) -> JSONResponse:
    logger.warning(
        "kis_api_error_unhandled",
        path=str(request.url.path),
        rt_cd=exc.rt_cd,
        msg=exc.msg,
    )
    return JSONResponse(
        status_code=502,
        content={"detail": f"KIS API 오류가 발생했습니다 (코드: {exc.rt_cd}). 잠시 후 다시 시도해주세요."},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.error(
        "unhandled_exception",
        path=str(request.url.path),
        error=_sanitize(str(exc)),
        exc_info=True,
    )
    return JSONResponse(status_code=500, content={"detail": "서버 오류가 발생했습니다."})


@app.get("/health")
async def health():
    db_ok = False
    redis_ok = False
    try:
        async for db in get_db():
            await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error("health_check_db_failed", error=str(e))

    try:
        redis = await get_redis()
        await redis.ping()
        redis_ok = True
    except Exception as e:
        logger.error("health_check_redis_failed", error=str(e))

    if db_ok and redis_ok:
        return {"status": "ok"}
    return JSONResponse(status_code=503, content={"status": "unavailable"})


@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint(request: Request) -> Response:
    if settings.metrics_token:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {settings.metrics_token}":
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    elif settings.app_env == "production":
        # 프로덕션에서 metrics_token 미설정 시 항상 차단
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
