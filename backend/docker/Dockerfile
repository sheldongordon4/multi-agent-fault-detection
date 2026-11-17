# syntax=docker/dockerfile:1
#
# MAFD API + Kafka consumers image.
#
# IMPORTANT: build from the repository ROOT, not backend/. The backend package
# imports scripts/ and ml/ (ml → scripts.load_testbed) and reads data/ (SOPs,
# models), so the build context must be the repo root:
#     docker compose -f docker-compose.dev.yaml up -d --build

FROM python:3.11-slim AS builder

# Pinned, not :latest — the installer should not change under a rebuild.
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Only the dependency declarations, so this layer is cached until they change.
COPY pyproject.toml uv.lock ./

# --frozen: install exactly what uv.lock pins, and fail rather than re-resolve.
#   Two builds of the same commit now produce the same versions; with the old
#   `>=` requirements.txt they did not.
# --no-dev: pytest / ruff / mypy stay out of the runtime image.
# CPU-only torch is no longer a separate pre-install step — [tool.uv.sources] in
# pyproject.toml pins torch to the CPU wheel index, so the lock already encodes
# it. The ~2 GB CUDA build is still what we are avoiding.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app \
    PATH="/opt/venv/bin:${PATH}" \
    HF_HOME=/opt/hf

WORKDIR ${APP_HOME}

# Runtime OS deps only (libgomp1 for scikit-learn/torch; curl for healthcheck).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# Bake the local embedding model so the KB builds offline at container start.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

COPY . .

# NOTE: WORKDIR /app is the container's install directory and has nothing to do
# with the package, which is now backend/. The build context is the repo ROOT, so
# `COPY . .` puts backend/ at /app/backend and ml/ at /app/ml — hence the
# backend/docker/ prefix here (same reason entrypoint.sh refers to
# backend/alembic.ini). The OS user below is also called app; also unrelated.
RUN chmod +x backend/docker/entrypoint.sh \
    && adduser --disabled-password --gecos "" app \
    && chown -R app:app ${APP_HOME} /opt/hf
USER app

EXPOSE 8000

# entrypoint waits for DB+Kafka, migrates, builds the KB, then runs the CMD.
ENTRYPOINT ["/app/backend/docker/entrypoint.sh"]
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
