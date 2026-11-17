# syntax=docker/dockerfile:1
#
# MAFD development image.
#
# Mirrors backend/docker/Dockerfile's dependency install (same Python 3.11, same
# locked versions, same baked embedding model) but keeps the dev group and the
# tooling the runtime image deliberately drops: compilers, psql, git, a shell.
#
# IMPORTANT: the build context is the repository ROOT, not .devcontainer/.
# See the note in .devcontainer/docker-compose.yml about path resolution.

ARG PYTHON_VARIANT=1-3.11-bookworm
FROM mcr.microsoft.com/devcontainers/python:${PYTHON_VARIANT}

# Pinned, not :latest — the installer should not change under a rebuild.
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    HF_HOME=/opt/hf

# build-essential + libgomp1: scikit-learn / torch / chromadb wheels and their
# OpenMP runtime. postgresql-client gives psql for poking at the dev database.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      libgomp1 \
      curl \
      postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/deps
COPY pyproject.toml uv.lock ./

# WITH the dev group (pytest, ruff, mypy) — unlike the runtime image, which
# syncs --no-dev. --frozen means the lock is authoritative: the dev container
# gets byte-identical versions to CI and to the shipped image.
#
# Dependencies live in /opt/venv, NOT in the workspace's .venv: the repo is bind
# mounted from Windows, where .venv holds Windows binaries that cannot run here.
# docker-compose.yml masks that directory so it can't be picked up by mistake.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen \
    && rm -rf /tmp/deps

WORKDIR /

# Bake the local embedding model so scripts/bootstrap.py and refresh_kb.py can
# build the SOP knowledge base without network access.
RUN mkdir -p /opt/hf \
    && /opt/venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')" \
    && chown -R vscode:vscode /opt/venv /opt/hf
