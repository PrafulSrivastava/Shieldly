# ShieldHer — local development shortcuts
#
# All commands that target running containers assume `make up` has been run.
# Run `make reset` for a full clean-slate setup from scratch.

.PHONY: up down migrate seed test logs shell reset createdb help

# ── Stack lifecycle ────────────────────────────────────────────────────────────

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f app

shell:
	docker compose exec app bash

# ── Database ───────────────────────────────────────────────────────────────────

migrate:
	docker compose exec app alembic upgrade head

## Create the test database (run once before the first `make test`)
createdb:
	docker compose exec db psql -U shieldher -d shieldher \
		-c "SELECT 1 FROM pg_database WHERE datname='shieldher_test'" \
		| grep -q 1 \
		|| docker compose exec db psql -U shieldher -d shieldher \
			-c "CREATE DATABASE shieldher_test"

seed:
	@echo "Seeding local DB…"
	curl -s -X POST http://localhost:8000/api/v1/dev/seed | python3 -m json.tool

# ── Testing ────────────────────────────────────────────────────────────────────
#
# `make test` runs inside the app container so Postgres and Redis are reachable
# via their compose service names (db, redis).  conftest.py will automatically
# create the shieldher_test DB if it doesn't exist.

test:
	docker compose exec app pytest tests/ -v

# Run a single test file, e.g.:  make test-file FILE=tests/test_auth.py
test-file:
	docker compose exec app pytest $(FILE) -v

# ── Full reset ─────────────────────────────────────────────────────────────────

reset: down
	docker compose up -d
	@echo "Waiting for services to become healthy…"
	sleep 8
	$(MAKE) migrate
	$(MAKE) seed

# ── Help ──────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "ShieldHer dev commands:"
	@echo ""
	@echo "  make up          Start all containers in the background"
	@echo "  make down        Stop all containers"
	@echo "  make migrate     Run Alembic migrations inside the app container"
	@echo "  make seed        POST /api/v1/dev/seed — wipe + re-seed local DB"
	@echo "  make test        Run pytest inside the app container"
	@echo "  make test-file   Run a single test file  (FILE=tests/test_auth.py)"
	@echo "  make logs        Tail app container logs"
	@echo "  make shell       Open a bash shell inside the app container"
	@echo "  make createdb    Create the shieldher_test DB (needed once)"
	@echo "  make reset       Full clean-slate: down → up → migrate → seed"
	@echo ""
