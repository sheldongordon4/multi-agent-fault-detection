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
uv sync                                          # deps from uv.lock, exact versions
alembic -c backend/alembic.ini upgrade head          # Alembic owns the schema
.venv/bin/python scripts/bootstrap.py            # topics + models + Chroma KB
uvicorn backend.api.main:app --reload                # host talks to kafka on localhost:29092
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

## Dev container (VS Code / any Dev Containers client)

A third way to run the stack: you work *inside* a container that sits on the same
`mafd-network` as Postgres and Kafka. "Reopen in Container" and you get Python
3.11 with every dependency installed, Node 22 + pnpm for the console, ruff,
pytest, alembic and psql — no host venv, no host Node, no port juggling.

```
.devcontainer/
  devcontainer.json    the Dev Containers config
  docker-compose.yml   overlay that adds the `devcontainer` service
  Dockerfile           the dev image
  post-create.sh       one-time setup, run after the container is created
```

**It starts `db`, `kafka` and `kafdrop` — not `app` or `client`.** You run uvicorn
and `pnpm dev` yourself, so the app service would be a second process on the same
Kafka `group.id`s and the same port 8000. `runServices` in `devcontainer.json`
pins that.

Once inside:

```bash
python scripts/bootstrap.py                        # topics + models + KB (once)
uvicorn backend.api.main:app --reload --host 0.0.0.0   # API + 6 consumer groups
cd frontend && pnpm dev --host                     # operator console
```

`post-create.sh` has already enabled corepack, run `pnpm install` and applied the
migrations. Ports 8000 and 5173 are forwarded to the host; Kafdrop (9000) and
Postgres (5433) are published by the base compose file as usual.

### Things worth knowing before you change it

- **Addressing inside the container is not the host's.** Postgres is `db:5432`,
  not `localhost:5433` — 5433 is only the published port that stops a native host
  Postgres shadowing the container. Kafka is `kafka:9092`, not `localhost:29092`.
  The overlay sets `DATABASE_ASYNC_URL` / `KAFKA_HOST` accordingly, matching the
  `app` service exactly.
- **Relative paths in `.devcontainer/docker-compose.yml` resolve from the repo
  root**, not from `.devcontainer/`. Compose resolves paths in a multi-file merge
  against the first `-f` file, and the base stack is listed first because later
  files must override earlier ones. That is why the overlay says
  `context: .` and `dockerfile: .devcontainer/Dockerfile`.
- **`.venv/` and `frontend/node_modules/` are masked by named volumes.** The repo
  is bind mounted from Windows, so both would otherwise expose Windows binaries
  that cannot run on Linux. The interpreter is `/opt/venv/bin/python`, pinned in
  `devcontainer.json` so nothing auto-selects the masked `.venv`.
- **Python dependencies come from `uv sync --frozen`**, the same lock the runtime
  image and CI use — so the dev container, the shipped image and the test runner
  agree on every version. The difference is the dev group: this image keeps
  pytest / ruff / mypy, the runtime one syncs `--no-dev`. CPU-only torch is in
  the lock (see `[tool.uv.sources]`), not a separate install step.
- The image also bakes `bge-small-en-v1.5` into `/opt/hf` (a named volume, so a
  rebuild doesn't re-download it) so the KB builds without network access.
- To change dependencies, edit `pyproject.toml` / run `uv add`, then rebuild the
  container — `uv sync` inside it writes to `/opt/venv`, which a rebuild discards.
- `docker compose -f docker-compose.dev.yaml -f .devcontainer/docker-compose.yml config`
  renders the merged file if you want to check a change — note it interpolates
  `.env` into its output, so don't paste the result anywhere.

## Configuration

- Secrets come from a project-root **`.env`** (mounted `required: false`, so the stack
  still boots without one — the Coordinator falls back to the offline heuristic ticket).
  Set `AZURE_OPENAI_*` there to enable the LLM path. See `.env.example`.
- In-container networking is overridden in compose (`KAFKA_HOST=kafka`,
  `KAFKA_PORT=9092`, container `DATABASE_ASYNC_URL` → `db:5432`).

## Image notes (`backend/docker/Dockerfile`)

- Multi-stage; **build from the repo root** (the `app` package imports `scripts/` and
  reads `data/`), not from `./app`.
- Installs with **`uv sync --frozen --no-dev`** from `pyproject.toml` + `uv.lock`:
  `--frozen` fails rather than re-resolving, so two builds of one commit install
  identical versions; `--no-dev` keeps pytest / ruff / mypy out of the runtime image.
- **CPU-only torch** comes from the lock, not a separate pre-install step —
  `[tool.uv.sources]` in `pyproject.toml` pins torch to the PyTorch CPU wheel index
  (avoids the ~2 GB CUDA build `sentence-transformers` would otherwise pull).
- **Bakes** the `bge-small-en-v1.5` embedding weights so the KB builds offline at
  container start. Runs as a non-root `app` user.
