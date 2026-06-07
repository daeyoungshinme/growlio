import structlog
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

logger = structlog.get_logger()

try:
    limiter = Limiter(key_func=get_remote_address, storage_uri=settings.redis_url)
except Exception as e:
    logger.warning("rate_limiter_redis_fallback", error=str(e))
    limiter = Limiter(key_func=get_remote_address)
