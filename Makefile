.PHONY: up down migrate install-backend install-frontend dev dev-backend dev-frontend \
        test-backend test-frontend lint typecheck \
        build-android-debug build-android-release

up:
	docker compose up -d db redis

down:
	docker compose down

migrate:
	cd backend && uv run alembic upgrade head

install-backend:
	cd backend && uv venv && uv pip install -e ".[dev]"

install-frontend:
	cd frontend && npm install

dev:
	bash dev.sh

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload

dev-frontend:
	cd frontend && npm run dev

test-backend:
	cd backend && uv run pytest

test-frontend:
	cd frontend && npm run test

lint:
	cd backend && uv run ruff check .
	cd frontend && npm run lint

typecheck:
	cd backend && uv run mypy app/
	cd frontend && npm run build

build-android-debug:
	cd frontend && npm run build && npx cap sync android
	cd frontend/android && gradlew.bat assembleDebug

build-android-release:
	cd frontend && npm run build && npx cap sync android
	cd frontend/android && gradlew.bat assembleRelease
