#!/usr/bin/env sh
# Container startup: wait for infra, migrate the schema, build the SOP KB, then
# exec the CMD (uvicorn). Idempotent — safe on every restart.
set -e

python - <<'PY'
import os
import socket
import time
from urllib.parse import urlparse


def wait(host, port, name, tries=60):
    for _ in range(tries):
        try:
            with socket.create_connection((host, int(port)), timeout=2):
                print(f"[entrypoint] {name} reachable at {host}:{port}", flush=True)
                return
        except OSError:
            time.sleep(2)
    raise SystemExit(f"[entrypoint] {name} not reachable at {host}:{port}")


db = urlparse(os.environ.get("DATABASE_ASYNC_URL", "postgresql+asyncpg://postgres:postgres@db:5432/mafd"))
wait(db.hostname or "db", db.port or 5432, "Postgres")
wait(os.environ.get("KAFKA_HOST", "kafka"), int(os.environ.get("KAFKA_PORT", "9092")), "Kafka")
PY

echo "[entrypoint] running database migrations..."
alembic -c app/alembic.ini upgrade head

echo "[entrypoint] building SOP knowledge base..."
python -c "from app.rag.vector_store import get_vectordb; get_vectordb(force_rebuild=True)"

echo "[entrypoint] starting: $*"
exec "$@"
