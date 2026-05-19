.PHONY: up down migrate install dev

up:
	docker compose up -d db redis

down:
	docker compose down

migrate:
	cd backend && alembic upgrade head

install-backend:
	cd backend && pip install uv && uv pip install -e ".[dev]"

install-frontend:
	cd frontend && npm install

dev-backend:
	cd backend && uvicorn app.main:app --reload

dev-frontend:
	cd frontend && npm run dev
