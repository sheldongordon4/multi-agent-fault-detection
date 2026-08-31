# AGENTS.md — Multi-Agent Fault Detection (MAFD)

Guidance for AI agents (and humans) working in this repository. Read this before making changes.

## Required reading

This file is a **summary**. Before any non-trivial work, also read the companion docs (they are the source of truth and stay ahead of this file):

- **`docs/System_Architecture.md`** — authoritative design, the as-built status + near-term TODO (§16), and open decisions (§14). Start here.
- **`docs/Agent_Architecture.md`** — the coordinator agent (detection-as-trigger, `kb_retrieve`, `FaultTicket`).
- **`docs/API_Reference.md`** — the HTTP endpoints.

If any of these disagree with this file, treat `docs/System_Architecture.md` as authoritative and reconcile.

---

##  Critical rules

- **NEVER read, open, print, or echo `.env` or any `.env.*` file** — they contain secrets (Azure keys, DB credentials). The **only** env file you may read is **`.env.example`** (placeholders only). Need a variable's meaning? Read `app/config.py` or `.env.example`.
- **Use the project venv**, not system Python: `.venv/Scripts/python.exe` (Windows). Don't install global packages.
- **Do not read the large testbed CSVs in full** (`data/testbed/**`, and the bigger `data/generated/*.csv`). They will flood context. Read only headers / first ~10 lines when you need the schema.
- **Don't commit, push, or change branches** unless explicitly asked. Never commit `.env`.
- The top-level package is **`app`** (this repo uses `app/`, not `src/`). Import as `from app.<domain> import ...`.

---

## What this project is

MAFD is a **fault detection, classification, and diagnosis** system for electrical power **distribution feeders**. It ingests grid signals, detects disturbances, retrieves the relevant **Standard Operating Procedure (SOP)**, and produces an explainable **FaultTicket** for operators. It is an **event-driven pipeline** of decoupled services connected by **Kafka**.

See `docs/System_Architecture.md` for the full target design and the as-built notes.

### As-built event pipeline

```
scripts/produce_events.py ─▶ feeder.events ─▶ [detection]  app/ml/fault_detector (IsolationForest)
                                                   │   + app/ml/fault_classifier (RandomForest: type/category/location)
                                                   │  publishes verdict + most-disturbed buses + classification
                                                   ▼
                                             anomalies.detected ─▶ [coordinator]  app/faults
                                                 │   Azure gpt-5.4-mini + kb_retrieve (RAG)
                                                   ▼
                                             faulttickets ─┬─▶ [notification]  SSE broadcast + Postgres
                                                           └─▶ [persistence]   Postgres (upsert) → GET /tickets

scripts/produce_signals.py ─▶ raw.signals ─▶ [streaming]  per-bus rolling buffer ─▶ SSE chart
```

**Detection-as-trigger:** detection runs *upstream*; the coordinator does NOT run detection. The coordinator's only LLM tool is `kb_retrieve`. Any handler that keeps failing routes the message to a `<topic>.dlq` dead-letter topic so it can't block the stream.

**The one missing link (see TODO):** the live `raw.signals → feeder.events` **feature-extraction worker** isn't built yet — today `produce_events.py` replays pre-reduced rows onto `feeder.events` directly.

---

## Tech stack

- **Python 3.11+** (venv currently 3.14), **FastAPI**, **Pydantic v2** + **pydantic-settings**
- **SQLAlchemy 2.0 (async)** + **asyncpg** + **Alembic** → **Postgres** (persistence)
- **confluent-kafka** (event bus); **Kafdrop** UI for inspection
- **LangChain** + **LangGraph** (ReAct agent), **Azure OpenAI** `gpt-5.4-mini` (coordinator LLM)
- **scikit-learn** IsolationForest (detection); **Streamlit** UI

Minimum versions to honor (per the best-practices AGENTS.md below): FastAPI 0.115, Pydantic 2.7, SQLAlchemy 2.0, Alembic 1.13, httpx 0.27, ruff 0.6.

---

## Project structure (domain-based)

```
app/
  config.py            global settings (pydantic-settings) — Azure, DB, Kafka, embeddings
  constants.py         Environment enum + DB naming convention
  database.py          async engine + fetch_one/fetch_all/execute helpers
  orm.py               SQLAlchemy DeclarativeBase + ULID/Timestamp mixins
  exceptions.py        DetailedHTTPException hierarchy
  utils.py             small helpers
  api/main.py          FastAPI app + lifespan (starts Kafka workers), /health, CORS

  faults/              COORDINATOR domain (diagnosis)
    router.py          POST /faults/diagnose  (response_model=FaultTicket)
    service.py         run_fault_diagnosis(detection) — Azure agent OR local heuristic fallback
    agent.py           LangGraph ReAct graph (AzureChatOpenAI + kb_retrieve)
    tools.py           kb_retrieve tool
    schemas.py         FaultTicket / EvidenceWindow / KBCitation / DiagnoseRequest / TopBus
    constants.py       SYSTEM_PROMPT

  faults/config.py     per-domain settings (Azure/LLM + rate-limit/retry/timeout)
  rag/config.py        per-domain settings (embedding model)
  notification/        incident alerts (router, service, models, schemas, sse, constants)
  streaming/           per-bus live signal SSE (manager, router)
  persistence/         FaultTicket → Postgres (models, service, schemas, router → GET /tickets)
  rag/                 SOP knowledge base (kb_loader, retriever, vector_store)  [support lib]
  simulation/          synthetic SCADA/relay generators  [support lib]
  kafka/               event infra: topics, producer, consumer, admin (topic mgmt), workers, handlers/
  ml/                  the models (moved from top-level ml/):
    fault_detector.py    PRIMARY detection — testbed event IsolationForest (per-bus feature rows)
    fault_classifier.py  supervised RandomForest — fault type / category / location
    feature_extractor.py raw 3-phase → event row bridge (1-cycle DFT implemented; streaming worker TODO)
    baseline_detector.py DEPRECATED legacy time-series IsolationForest — scripts-only, NOT in the app
  alembic/ + alembic.ini   migrations

docker/    Dockerfile + entrypoint.sh (waits for infra → migrate → build KB → uvicorn)
scripts/   bootstrap.py (topics+models+KB), produce_events.py, produce_events_live.py, produce_signals.py, refresh_kb.py, generate_*, validate_*
data/      sop/ (SOP .md)  synthetic/ (LEGACY, deprecating)  generated/ (normal_train, validation)  testbed/ (LARGE — see rules)
docs/      System_Architecture.md (authoritative), API_Reference.md, Agent_Architecture.md
frontend/  React operator console (Vite + React 19 + Tailwind v4 + shadcn/Radix, TanStack Query, Zustand).
           features/{incidents,map,overview}/ · shared/ · app/{routes,layouts,store}
           Map stack: MapLibre GL + react-map-gl + pmtiles, with a SELF-HOSTED offline
           Jamaica basemap in public/map/ (see frontend/README.md — do not delete those
           assets, they are the basemap). Incidents is the index route; the old
           /overview page is gone (it's a bottom drawer on Incidents now).
ui/        streamlit_app.py (reads ticket JSON; not SSE-wired yet)
tests/     test_api.py (AsyncClient+ASGITransport), test_feature_extractor.py, test_fault_ticket_schema.py, test_health.py
```

---

## Best practices to follow

Source: **https://github.com/zhanymkanov/fastapi-best-practices** (its `README.md` and `AGENTS.md`). Key rules, adapted to this repo (`app/` instead of `src/`):

- **Domain structure.** Each domain package holds `router.py`, `schemas.py` (Pydantic), `models.py` (ORM), `service.py` (business logic), `dependencies.py`, `constants.py`, `config.py`, `exceptions.py`, `utils.py`. Keep routers thin; logic lives in `service.py`. Import with top-level module names (`from app.faults import service as faults_service`) — no deep cross-domain or wildcard imports.
- **Async correctness.** Never run blocking I/O (`requests`, `time.sleep`, sync DB, `open()`) inside `async def` — it freezes the event loop. Use `async def` + `await` for I/O; wrap blocking/sync SDK calls in `asyncio.to_thread` / `run_in_threadpool`; offload CPU-bound work (>50ms) to a worker. (The Kafka handlers already `to_thread` the LLM + sklearn calls.)
- **Dependencies.** Use the `Annotated[T, Depends(...)]` form, not default-arg `Depends()`. Validate inside dependencies; chain them for reuse.
- **Pydantic.** Use built-in validators / `Field` constraints / `StrEnum`; don't mix `Field(ge=…, default=None)`; use `@field_serializer` (not `json_encoders`). **One `BaseSettings` per domain** (see TODO — we currently centralize).
- **Routes.** Always set `response_model`, `status_code`, `tags`, `summary`/`description`. Hide docs outside dev.
- **Database.** SQLAlchemy 2.0 async (`AsyncConnection`); tables lowercase snake_case singular; consistent FK names; explicit MetaData naming convention (already in `app/constants.py`); SQL-first (joins/aggregation in DB).
- **Migrations.** Alembic owns the schema (`alembic -c app/alembic.ini upgrade head`). Migrations static + reversible; filenames `YYYY-MM-DD_slug.py` (configured). Don't use `create_all` in app startup.
- **Tests.** `httpx.AsyncClient` + `ASGITransport`; override deps via `app.dependency_overrides`; real DB in integration tests (don't mock the DB).
- **Lint/format.** Ruff (`ruff check --fix` / `ruff format`) — config in `pyproject.toml`.
- **Auth note:** this project intentionally has **no auth/users** (operator dashboard). SSE is broadcast (notifications) or per-bus (streaming). Do not reintroduce per-user auth.

---

## Project-specific conventions

- **Models:** coordinator → Azure `gpt-5.4-mini`; embeddings → local `bge-small` (offline). If `AZURE_OPENAI_*` is unset/placeholder, `run_fault_diagnosis` returns a **local heuristic ticket** (no LLM) — this is intentional, keep it working.
- **Detection-as-trigger:** the coordinator never calls a detection tool; it diagnoses the `anomalies.detected` payload (`feeder`, `verdict`, `topBuses`) and only calls `kb_retrieve`.
- **Idempotency:** `incident_id` keys the ticket; persistence upserts (at-least-once Kafka delivery → overwrite, not duplicate).
- **Kafka:** five consumer groups for fan-out (`detection`, `streaming`, `coordinator`, `notification`, `persistence`); `run_consumer(group_id, handlers)` is generic. Partition by `feeder`/`bus_id`/`incident_id`.
- **Embedding dim change requires a KB rebuild** (`scripts/refresh_kb.py`).

---

## Running locally

**Everything in Docker** (the `app` service self-migrates + builds the KB via `docker/entrypoint.sh`):
```bash
docker compose -f docker-compose.dev.yaml up -d --build   # db + kafka + kafdrop(:9000) + app(:8000)
.venv/Scripts/python.exe scripts/produce_events.py        # host producer → container pipeline
```

**App on the host, infra in Docker:**
```bash
docker compose -f docker-compose.dev.yaml up -d db kafka kafdrop
.venv/Scripts/python.exe -m pip install -r requirements.txt
alembic -c app/alembic.ini upgrade head                # create schema (Alembic owns it)
.venv/Scripts/python.exe scripts/bootstrap.py          # topics + models + Chroma KB
# set AZURE_OPENAI_* in .env (else the coordinator returns a heuristic ticket)
uvicorn app.api.main:app --reload                      # API + 5 consumer groups; /ready checks DB+Kafka
.venv/Scripts/python.exe scripts/produce_events.py     # drives detection → coordinator → tickets
```
Don't run the host `uvicorn` and the container `app` at once — same Kafka `group.id`s + a port-8000 clash.
Gotcha: a native host Postgres on `:5432` can shadow the container's — the app-in-container uses the container DB (`db:5432`).

---

## TODO — near-term

**Top priority — the last stubbed link:**
- [ ] **Feature-extraction worker** — a 6th Kafka consumer group on `raw.signals` that feeds each sample into a per-feeder `FeatureExtractor`, windows per bus, `reduce_to_row()`, and publishes the event row to `feeder.events`. Then `detect.py` scores `fault_detector` + `fault_classifier` off it (unchanged). This makes detection **live** instead of `produce_events.py` replaying pre-reduced rows.
  - **Open decision A:** `raw.signals` must become **3-phase waveforms** (`{t, bus, Va,Vb,Vc,Ia,Ib,Ic}` at ~kHz) — the DSP can't compute `I0/I1`, `I2/I1` from single-magnitude SCADA. Confirm the schema change + add a waveform producer.
  - **Open decision B:** the live chart currently plots the SCADA `raw.signals`. If it becomes waveforms, plot the waveform (Va/Ia), plot the reduced per-bus features, or park the chart.

**Deprecations (planned):**
- [ ] **Retire `app/ml/baseline_detector.py`** (time-series IsolationForest) + the **old synthetic data/DB** (`data/synthetic/*`, `synthetic_signals.db`). Only `scripts/run_detection_demo.py` still uses them. Dropping this also strands `produce_signals.py` + the streaming chart (see decision B).

**Other gaps:**
- [ ] **Streamlit UI is not SSE-wired** — it reads ticket JSON files; connect it to `/notifications/stream` and `/stream/signals`.
- [ ] **Reconcile the bus namespaces.** Streaming uses `bus_1/2/3` (legacy synthetic), the event path stamps IEEE13 ids (`b632/b650/b671/b675/b684`) on every ticket, so nothing joins the two. It's a symptom of the missing feature-extraction worker above — don't "fix" it by renaming `BUS_IDS`, which hides the gap and invests in data we're retiring. Now visible in the console, which shows both on one screen.
- [ ] **Notification email/external channels** — only in-process SSE broadcast exists; no email/SMS/webhook delivery.
- [ ] **Feeder-agnostic classifier** — `fault_classifier` is feeder-specific (13-bus columns); §6.1 wants topology-independent aggregate features so it transfers to new feeders.

**Done (for reference):** **concurrency isolation** (`app/kafka/executors.py` — dedicated Kafka thread pool + ML `ProcessPoolExecutor`; fixed the live chart freezing while events processed) · **fast-path streaming consumer** (batched auto-commit for `raw.signals`; at-most-once for that topic only) · **React operator console** (`frontend/` — map-first incidents screen) · event/`fault_detector` detection · supervised `fault_classifier` (type/category/location, attached to `anomalies.detected`) · coordinator (Azure `gpt-5.4-mini` + `kb_retrieve`, rate-limited + bounded retries, heuristic fallback) · per-domain configs · `StrEnum` `FaultTicket` · `feature_extractor` DSP (1-cycle DFT) · DLQ on all topics · `GET /tickets` + `/tickets/{id}` history API · `/ready` (DB+Kafka) · Alembic migration · Kafka topic bootstrap · Dockerfile + self-bootstrapping entrypoint · integration tests.