FROM python:3.11-slim AS builder
WORKDIR /app
RUN pip install uv
COPY pyproject.toml uv.lock ./
COPY app/ ./app/
RUN uv venv /venv \
    && uv export --frozen --no-dev --no-hashes --output-file requirements.txt \
    && uv pip install --python /venv/bin/python -r requirements.txt

FROM python:3.11-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
RUN adduser --disabled-password --gecos '' appuser
COPY --from=builder /venv /venv
COPY --chown=appuser:appuser . .
USER appuser
ENV PATH="/venv/bin:$PATH"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
