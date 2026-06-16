import structlog
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

logger = structlog.get_logger()

try:
    limiter = Limiter(key_func=get_remote_address, storage_uri=settings.redis_url)
except Exception as e:
    # Redis-backed limiter 초기화 실패 시 in-memory fallback — 멀티 인스턴스 환경에서 rate limit 공유 불가
    logger.error("rate_limiter_redis_fallback", error=str(e), fallback="in_memory")
    limiter = Limiter(key_func=get_remote_address)
