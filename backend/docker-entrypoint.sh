#!/bin/sh
# Roda as migrations do Alembic antes de subir o servidor — garante que um
# banco novo (ex.: Postgres recém-criado na nuvem) fique com o schema em dia
# sem precisar de passo manual.
set -e

alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
