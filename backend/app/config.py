import re
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    app_env: str = "development"
    app_secret_key: str
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/growlio"
    redis_url: str = "redis://localhost:6379/0"

    kis_cred_encryption_key: str  # 32-byte hex (64자), AES-256 암호화 키

    allowed_origins: str = "http://localhost:5173"

    # Supabase
    supabase_project_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # 외부 API 동시 호출 제한 및 캐시 설정
    api_semaphore_limit: int = 5
    redis_cache_ttl_seconds: int = 3600
    usd_krw_fallback_rate: float = 1300.0

    # DB 커넥션 풀 설정
    database_pool_size: int = 10
    database_max_overflow: int = 5
    database_pool_timeout: int = 30
    slow_query_ms: int = 200  # 이 임계값(ms) 초과 쿼리는 경고 로그 출력

    dart_api_key: str = ""  # .env의 DART_API_KEY로 설정 (opendart.fss.or.kr)

    open_banking_client_id: str = ""
    open_banking_client_secret: str = ""
    open_banking_redirect_uri: str = "http://localhost:8000/api/v1/open-banking/callback"
    open_banking_base_url: str = "https://testapi.openbanking.or.kr"

    # SMTP (이메일 알림)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "growlio@example.com"

    frontend_url: str = "http://localhost:5173"

    # Sentry 에러 추적 (비어 있으면 비활성화)
    sentry_dsn: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        origins = [o.strip() for o in self.allowed_origins.split(",")]
        if self.app_env == "production":
            for o in origins:
                if not o.startswith("https://"):
                    raise ValueError(f"CORS origin must use HTTPS in production: {o}")
        return origins

    @model_validator(mode="after")
    def _validate_secrets(self) -> "Settings":
        if not self.app_secret_key or len(self.app_secret_key) < 32:
            raise ValueError("APP_SECRET_KEY must be at least 32 characters")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", self.kis_cred_encryption_key):
            raise ValueError("KIS_CRED_ENCRYPTION_KEY must be exactly 64 hex characters")
        if all(c == "0" for c in self.kis_cred_encryption_key):
            raise ValueError(
                "KIS_CRED_ENCRYPTION_KEY must not be all zeros — "
                "generate with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
            )
        # supabase_jwt_secret은 RS256 JWKS 방식 사용 시 불필요 (선택적)
        return self


settings = Settings()
