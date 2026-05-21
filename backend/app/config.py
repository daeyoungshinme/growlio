from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret_key: str
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/growlio"
    redis_url: str = "redis://localhost:6379/0"

    kis_cred_encryption_key: str  # 32-byte hex (64자), AES-256 암호화 키

    allowed_origins: str = "http://localhost:5173"

    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # 외부 API 동시 호출 제한 및 캐시 설정
    api_semaphore_limit: int = 5
    redis_cache_ttl_seconds: int = 3600
    usd_krw_fallback_rate: float = 1300.0

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

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
