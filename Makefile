# Makefile
.PHONY: up down dev logs ps clean reset shell-api shell-neo4j init-schema

# ── Start ──────────────────────────────────────────────────────────────────
up:
	docker compose up -d
	@echo "Services started. API: http://localhost:8000/docs"
	@echo "Neo4j Browser: http://localhost:7474"

# ── Development mode dengan hot-reload ────────────────────────────────────
dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# ── Stop ───────────────────────────────────────────────────────────────────
down:
	docker compose down

# ── Logs ───────────────────────────────────────────────────────────────────
logs:
	docker compose logs -f

logs-api:
	docker compose logs -f fastapi

logs-neo4j:
	docker compose logs -f neo4j

# ── Status ─────────────────────────────────────────────────────────────────
ps:
	docker compose ps

# ── Shell access ───────────────────────────────────────────────────────────
shell-api:
	docker compose exec fastapi bash

shell-neo4j:
	docker compose exec neo4j cypher-shell \
	  -u neo4j -p $${NEO4J_PASSWORD:-kg_password_2024}

shell-redis:
	docker compose exec redis redis-cli

# ── Schema migration manual ────────────────────────────────────────────────
init-schema:
	docker compose run --rm neo4j-init

# ── Build ulang FastAPI image ──────────────────────────────────────────────
build:
	docker compose build fastapi

# ── Hard reset: hapus semua data ──────────────────────────────────────────
reset:
	@read -p "Hapus semua data Neo4j dan Redis? [y/N] " ans; \
	[ "$$ans" = "y" ] && docker compose down -v || echo "Cancelled."

# ── Health check ───────────────────────────────────────────────────────────
health:
	@curl -s http://localhost:8000/health | python3 -m json.tool

# ── Backup Neo4j data ──────────────────────────────────────────────────────
backup:
	@mkdir -p ./backups
	docker compose exec neo4j neo4j-admin database dump neo4j \
	  --to-path=/tmp/backup.dump
	docker compose cp neo4j:/tmp/backup.dump \
	  ./backups/neo4j_$(shell date +%Y%m%d_%H%M%S).dump
	@echo "Backup saved to ./backups/"