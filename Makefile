BACKEND_DIR := backend
VENV        := $(BACKEND_DIR)/.venv
PYTHON      := $(VENV)/bin/python3
ALEMBIC     := $(PYTHON) -m alembic
UVICORN     := $(PYTHON) -m uvicorn
COMPOSE     := docker compose

# ─── Docker / Infra ──────────────────────────────────────────────────────────

.PHONY: db-up db-down db-logs db-shell

db-up:
	$(COMPOSE) up -d db

db-down:
	$(COMPOSE) down

db-logs:
	$(COMPOSE) logs -f db

db-shell:
	$(COMPOSE) exec db psql -U barrio -d barrio

# ─── Migrations ──────────────────────────────────────────────────────────────

.PHONY: migrate-gen migrate-up migrate-down migrate-history migrate-current

migrate-gen:
	@read -p "Nome da migration: " name; \
	cd $(BACKEND_DIR) && $(ALEMBIC) revision --autogenerate -m "$$name"

migrate-up:
	cd $(BACKEND_DIR) && $(ALEMBIC) upgrade head

migrate-down:
	cd $(BACKEND_DIR) && $(ALEMBIC) downgrade -1

migrate-history:
	cd $(BACKEND_DIR) && $(ALEMBIC) history --verbose

migrate-current:
	cd $(BACKEND_DIR) && $(ALEMBIC) current

# ─── Backend dev ──────────────────────────────────────────────────────────────

.PHONY: dev install

install:
	cd $(BACKEND_DIR) && python -m venv .venv && $(PYTHON) -m pip install -r requirements.txt

dev:
	cd $(BACKEND_DIR) && $(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload

# ─── Validação ───────────────────────────────────────────────────────────────

.PHONY: validate-models validate-db

validate-models:
	cd $(BACKEND_DIR) && $(PYTHON) -W all -c "\
import sys; sys.path.insert(0, '.'); \
import app.models; \
from sqlalchemy.orm import configure_mappers; \
from app.database.base import Base; \
configure_mappers(); \
tables = list(Base.metadata.tables.keys()); \
print(f'OK: {len(tables)} tabelas - {tables}')"

validate-db:
	cd $(BACKEND_DIR) && $(PYTHON) -c "\
import sys, asyncio; sys.path.insert(0, '.'); \
from app.database.session import engine; \
from sqlalchemy import text; \
async def check(): \
    async with engine.connect() as conn: \
        r = await conn.execute(text('SELECT version()')); \
        print('PostgreSQL:', r.scalar()); \
asyncio.run(check())"
