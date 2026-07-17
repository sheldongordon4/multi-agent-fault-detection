# syntax=docker/dockerfile:1
#
# MAFD API + Kafka consumers image.
#
# IMPORTANT: build from the repository ROOT, not app/. The app package imports
# scripts/ (app.ml → scripts.load_testbed) and reads data/ (SOPs, models), so the
# build context must be the repo root:
#     docker compose -f docker-compose.dev.yaml up -d --build

FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install CPU-only torch first — it's ~2 GB smaller than the default CUDA build
# that sentence-transformers would otherwise pull in.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
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

RUN chmod +x docker/entrypoint.sh \
    && adduser --disabled-password --gecos "" app \
    && chown -R app:app ${APP_HOME} /opt/hf
USER app

EXPOSE 8000

# entrypoint waits for DB+Kafka, migrates, builds the KB, then runs the CMD.
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
