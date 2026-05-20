FROM python:3.11-slim AS builder
WORKDIR /app
RUN pip install uv
COPY pyproject.toml .
COPY app/ ./app/
RUN uv venv /venv && uv pip install --python /venv/bin/python .

FROM python:3.11-slim AS runtime
WORKDIR /app
RUN adduser --disabled-password --gecos '' appuser
COPY --from=builder /venv /venv
COPY --chown=appuser:appuser . .
USER appuser
ENV PATH="/venv/bin:$PATH"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
