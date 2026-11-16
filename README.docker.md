# Running MAFD with Docker

`docker-compose.dev.yaml` brings up the full local stack: **Postgres** (persistence),
**Kafka** (event bus, KRaft mode — no ZooKeeper), **Kafdrop** (topic inspection UI),
and the **app** (FastAPI API + the 6 Kafka consumer groups).

## Services & ports

| Service | Port (host) | Notes |
| ------- | ----------- | ----- |
| `app` | `8000` | FastAPI + consumers; `/health`, `/ready`, `/docs` |
| `db` | `5433` | Postgres 18 (`postgres` / `postgres`, db `mafd`); in-network clients use `db:5432` |
| `kafka` | `29092` | EXTERNAL listener for host clients; in-network clients use `kafka:9092` |
| `kafdrop` | `9000` | browse topics, partitions, and the `.dlq` dead-letter topics |

## Everything in Docker

The `app` container self-bootstraps via `docker/entrypoint.sh`: it waits for
Postgres + Kafka, runs Alembic migrations, builds the SOP knowledge base, then
starts uvicorn.

```bash
docker compose -f docker-compose.dev.yaml up -d --build
# drive the whole chain from the host, starting at raw.signals:
.venv/bin/python scripts/produce_waveforms.py --fault SLG
# or skip extraction and replay pre-reduced rows onto feeder.events:
.venv/bin/python scripts/produce_events.py
```

Check readiness and watch the pipeline:

```bash
curl -fsS http://localhost:8000/ready     # {"ready": true, "checks": {...}}
# open http://localhost:9000 (Kafdrop) to see raw.signals → feeder.events → anomalies.detected → faulttickets
```

## Infra in Docker, app on the host

Useful for iterating on the app with `--reload`:

```bash
docker compose -f docker-compose.dev.yaml up -d db kafka kafdrop
.venv/bin/python -m pip install -r requirements.txt
alembic -c app/alembic.ini upgrade head          # Alembic owns the schema
.venv/bin/python scripts/bootstrap.py            # topics + models + Chroma KB
uvicorn app.api.main:app --reload                # host talks to kafka on localhost:29092
.venv/bin/python scripts/produce_waveforms.py --fault SLG
```

> Don't run the host `uvicorn` **and** the container `app` at once — they share Kafka
> `group.id`s and both bind port 8000.
>
> The container DB is published on **`5433`**, not 5432, precisely so a native host
> Postgres can't shadow it. Host clients (the app on the host, `alembic`, psql) use
> `localhost:5433`; in-container clients use `db:5432`. If you point a host client at
> 5432 you may silently reach a *different* database — and the real-DB integration
> tests skip rather than fail when nothing is listening, so check for `skipped` in
> the pytest summary.

## Configuration

- Secrets come from a project-root **`.env`** (mounted `required: false`, so the stack
  still boots without one — the Coordinator falls back to the offline heuristic ticket).
  Set `AZURE_OPENAI_*` there to enable the LLM path. See `.env.example`.
- In-container networking is overridden in compose (`KAFKA_HOST=kafka`,
  `KAFKA_PORT=9092`, container `DATABASE_ASYNC_URL` → `db:5432`).

## Image notes (`docker/Dockerfile`)

- Multi-stage; **build from the repo root** (the `app` package imports `scripts/` and
  reads `data/`), not from `./app`.
- Installs **CPU-only torch** before `requirements.txt` (avoids the ~2 GB CUDA build
  that `sentence-transformers` would otherwise pull).
- **Bakes** the `bge-small-en-v1.5` embedding weights so the KB builds offline at
  container start. Runs as a non-root `app` user.
