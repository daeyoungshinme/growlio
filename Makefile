.PHONY: up down migrate migrate-down install-backend install-frontend dev dev-keep-port dev-backend dev-frontend \
        test-backend test-backend-cov test-frontend lint typecheck \
        clean format format-backend db-reset \
        build-android-debug build-android-release

up:
	docker compose up -d db

down:
	docker compose down

migrate:
	cd backend && uv run alembic upgrade head

migrate-down:
	cd backend && uv run alembic downgrade -1

install-backend:
	cd backend && uv sync --extra dev
	pre-commit install

format-backend:
	cd backend && uv run ruff format . && uv run ruff check . --fix

install-frontend:
	cd frontend && npm install

dev:
	bash dev.sh

dev-keep-port:
	bash dev.sh --keep-port

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload

dev-frontend:
	cd frontend && npm run dev

test-backend:
	cd backend && uv run pytest

test-backend-cov:
	cd backend && uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=80

test-frontend:
	cd frontend && npm run test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && \
	cd ../frontend && npm run lint -- --max-warnings 0 && npm run format:check

typecheck:
	cd backend && uv run mypy app/ && \
	cd ../frontend && npx tsc --noEmit

clean:
	rm -rf frontend/dist backend/.pytest_cache backend/.ruff_cache

format: format-backend
	cd frontend && npm run format

db-reset:
	@echo "WARNING: This will DELETE all database data (docker volumes)!"
	@echo "Press Ctrl+C to cancel, or wait 5 seconds to continue..."
	@sleep 5
	docker compose down -v && docker compose up -d db && sleep 3 && $(MAKE) migrate

build-android-debug:
	cd frontend && npm run build && npx cap sync android
	cd frontend/android && gradlew.bat assembleDebug

build-android-release:
	cd frontend && npm run build && npx cap sync android
	cd frontend/android && gradlew.bat assembleRelease
