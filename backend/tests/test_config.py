"""app.core.config.Settings 검증 로직 테스트."""

import pytest

from app.core.config import Settings


def test_production_with_localhost_frontend_url_raises():
    with pytest.raises(ValueError, match="FRONTEND_URL"):
        Settings(app_env="production", frontend_url="http://localhost:5173")


_SUPABASE = {
    "supabase_project_url": "https://abc.supabase.co",
    "supabase_anon_key": "anon",
    "supabase_service_role_key": "service",
}


def test_production_with_https_frontend_url_succeeds():
    settings = Settings(app_env="production", frontend_url="https://growlio.vercel.app", **_SUPABASE)
    assert settings.frontend_url == "https://growlio.vercel.app"


def test_production_without_supabase_settings_raises():
    """비어 있으면 앱은 떠도 모든 요청이 401 — 기동 시점에 실패해야 한다."""
    with pytest.raises(ValueError, match="SUPABASE_SERVICE_ROLE_KEY"):
        Settings(
            app_env="production",
            frontend_url="https://growlio.vercel.app",
            **{**_SUPABASE, "supabase_service_role_key": ""},
        )


def test_development_with_localhost_frontend_url_succeeds():
    settings = Settings(app_env="development", frontend_url="http://localhost:5173")
    assert settings.frontend_url == "http://localhost:5173"
