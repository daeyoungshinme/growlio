from slowapi import Limiter
from slowapi.util import get_remote_address

# in-memory storage — 단일 인스턴스(Render free plan) 배포라 인스턴스 간 rate limit 공유가 불필요.
# Redis-backed storage는 요청마다 Redis 커맨드를 소모해 Upstash 월간 한도를 빠르게 소진시켰다.
limiter = Limiter(key_func=get_remote_address)
