"""app.config.Settings 검증 로직 테스트."""

import pytest

from app.config import Settings


def test_production_with_localhost_frontend_url_raises():
    with pytest.raises(ValueError, match="FRONTEND_URL"):
        Settings(app_env="production", frontend_url="http://localhost:5173")


def test_production_with_https_frontend_url_succeeds():
    settings = Settings(app_env="production", frontend_url="https://growlio.vercel.app")
    assert settings.frontend_url == "https://growlio.vercel.app"


def test_development_with_localhost_frontend_url_succeeds():
    settings = Settings(app_env="development", frontend_url="http://localhost:5173")
    assert settings.frontend_url == "http://localhost:5173"
