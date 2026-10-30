FROM ghcr.io/astral-sh/uv:0.11.15 AS uv

FROM python:3.13-slim AS builder
WORKDIR /app
COPY --from=uv /uv /bin/uv
COPY pyproject.toml uv.lock ./
# 프로젝트 자체는 설치하지 않는다 — 의존성 레이어가 app/ 변경에 무효화되지 않게
RUN UV_PROJECT_ENVIRONMENT=/venv uv sync --locked --no-dev --no-install-project

FROM python:3.13-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
RUN adduser --disabled-password --gecos '' appuser
COPY --from=builder /venv /venv
COPY --chown=appuser:appuser . .
USER appuser
# 프로젝트를 설치하지 않으므로 scripts/*(preDeploy의 bootstrap_alembic.py)의 `import app`이 이 경로에 의존한다
ENV PATH="/venv/bin:$PATH" PYTHONPATH=/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
