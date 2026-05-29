import re
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import router
from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.redis_client import close_redis, get_redis
from app.scheduler import init_scheduler, scheduler

logger = structlog.get_logger()

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
        await redis.ping()
        logger.info("redis_connected")
    except Exception as e:
        logger.error("redis_startup_failed", error=str(e))
        raise RuntimeError(f"Redis에 연결할 수 없습니다: {e}") from e

    init_scheduler()
    logger.info("app_started", env=settings.app_env)
    yield
    scheduler.shutdown()
    await close_redis()
    logger.info("app_stopped")


app = FastAPI(
    title="Growlio — 자산관리 + 적립식 자동매매",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env == "development" else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

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
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start) * 1000)
    request_id = getattr(request.state, "request_id", "-")
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
        request_id=request_id,
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.error("unhandled_exception", path=str(request.url.path), error=_sanitize(str(exc)), exc_info=True)
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
