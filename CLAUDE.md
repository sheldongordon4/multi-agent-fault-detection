# CLAUDE.md — Multi-Agent Fault Detection (MAFD)

Guidance for AI agents (and humans) working in this repository. Read this before making changes.

## Required reading

This file is a **summary**. Before any non-trivial work, also read the companion docs (they are the source of truth and stay ahead of this file):

- **`docs/System_Architecture.md`** — authoritative design, the as-built status + near-term TODO (§16), and open decisions (§14). Start here.
- **`docs/AGENT_ARCHITECTURE.md`** — the coordinator agent (detection-as-trigger, `kb_retrieve`, `FaultTicket`).
- **`docs/API_Reference.md`** — the HTTP endpoints.

If any of these disagree with this file, treat `docs/System_Architecture.md` as authoritative and reconcile.

---

##  Critical rules

- **NEVER read, open, print, or echo `.env` or any `.env.*` file** — they contain secrets (LLM API keys, DB credentials). The **only** env file you may read is **`.env.example`** (placeholders only). Need a variable's meaning? Read `backend/config.py` or `.env.example`.
- **Dependencies are managed by `uv`** — `pyproject.toml` declares them, `uv.lock` pins them, and there is no `requirements.txt`. `uv sync` creates/updates `.venv`; run things with `uv run ...` or `.venv/Scripts/python.exe` (Windows) directly. **Never `pip install` into the venv** — it drifts from the lock and the next `uv sync` undoes it. Add a dependency with `uv add <pkg>` (`--dev` for tooling), which updates both files. Don't install global packages.
- **Do not read the large testbed CSVs in full** (`data/testbed/**`, and the bigger `data/generated/*.csv`). They will flood context. Read only headers / first ~10 lines when you need the schema.
- **Don't commit, push, or change branches** unless explicitly asked. Never commit `.env`.
- The backend package is **`backend/`** (not `src/`, and no longer `app/`), with the ML layer as a **top-level `ml/`** package beside it. Import as `from backend.<domain> import ...` and `from ml.<module> import ...`. Note the compose service and the container path `/app` are still called app — neither is the package.

---

## What this project is

MAFD is a **fault detection, classification, and diagnosis** system for electrical power **distribution feeders**. It ingests grid signals, detects disturbances, retrieves the relevant **Standard Operating Procedure (SOP)**, and produces an explainable **FaultTicket** for operators. It is an **event-driven pipeline** of decoupled services connected by **Kafka**.

See `docs/System_Architecture.md` for the full target design and the as-built notes.

### As-built event pipeline

```
scripts/produce_waveforms.py ─▶ raw.signals ─▶ [extraction]  backend/kafka/handlers/extract
                                                   │   FeatureExtractor: 1-cycle DFT → reduced row
                                                   ▼
                                             feeder.events ─▶ [detection]  ml/fault_detector (IsolationForest)
                                                   │   + ml/fault_classifier (RandomForest: type/category/location)
                                                   │  publishes verdict + most-disturbed buses + classification
                                                   ▼
                                             anomalies.detected ─▶ [coordinator]  backend/faults
                                                 │   Gemini + kb_retrieve (RAG)
                                                   ▼
                                             faulttickets ─┬─▶ [notification]  SSE broadcast + Postgres
                                                           └─▶ [persistence]   Postgres (upsert) → GET /tickets

                    raw.signals ─▶ [streaming]  per-cycle RMS ─▶ SSE chart

(scripts/produce_events.py still replays pre-reduced rows onto feeder.events for
offline work — it bypasses extraction by design.)
```

**Detection-as-trigger:** detection runs *upstream*; the coordinator does NOT run detection. The coordinator's only LLM tool is `kb_retrieve`. Any handler that keeps failing routes the message to a `<topic>.dlq` dead-letter topic so it can't block the stream.

**`raw.signals` carries 3-phase WAVEFORM frames**, not scalar SCADA readings — sequence ratios (I0/I1, I2/I1) need all three phases. One frame = one cycle for one bus (`backend/kafka/waveform.py`); batching per cycle keeps the topic at ~60 msg/s/bus instead of ~2k. The `extraction` consumer group reduces frames to event rows, so signals now reach tickets end to end.

---

## Tech stack

- **Python 3.11+** (venv currently 3.14), **FastAPI**, **Pydantic v2** + **pydantic-settings**
- **SQLAlchemy 2.0 (async)** + **asyncpg** + **Alembic** → **Postgres** (persistence)
- **confluent-kafka** (event bus); **Kafdrop** UI for inspection
- **LangChain** + **LangGraph** (ReAct agent); coordinator LLM is **Google AI Studio** `gemini-3.8-flash` by default (native `langchain-google-genai`), or **any OpenAI-compatible endpoint** via `ChatOpenAI`
- **scikit-learn** IsolationForest (detection); **React 19 + Vite** operator console (`frontend/`) — the Streamlit browser and its dependency are gone

Minimum versions to honor (per the best-practices AGENTS.md below): FastAPI 0.115, Pydantic 2.7, SQLAlchemy 2.0, Alembic 1.13, httpx 0.27, ruff 0.6.

---

## Project structure (domain-based)

```
backend/
  config.py            global settings (pydantic-settings) — DB, Kafka, embeddings
  constants.py         Environment enum + DB naming convention
  database.py          async engine + fetch_one/fetch_all/execute helpers
  orm.py               SQLAlchemy DeclarativeBase + ULID/Timestamp mixins
  exceptions.py        DetailedHTTPException hierarchy
  utils.py             small helpers
  api/main.py          FastAPI app + lifespan (starts Kafka workers), /health, CORS

  faults/              COORDINATOR domain (diagnosis)
    router.py          POST /faults/diagnose  (response_model=FaultTicket)
    service.py         run_fault_diagnosis(detection) — LLM agent OR local heuristic fallback
    agent.py           LangGraph ReAct graph + build_chat_model() (Google native OR ChatOpenAI) + kb_retrieve
    tools.py           kb_retrieve tool
    schemas.py         FaultTicket / EvidenceWindow / KBCitation / DiagnoseRequest / TopBus
    constants.py       SYSTEM_PROMPT

  assignments/         TICKET OWNERSHIP (operators, work state, activity log)
    models.py          Operator (roster, NOT accounts) / TicketAssignment / AssignmentEvent
    router.py          GET|POST /operators · GET /assignments · PATCH /assignments/{id}
    service.py         assignment reads/writes; the redelivery invariant lives here
    constants.py       WorkState / Priority / OperatorRole / EventKind enums

  faults/config.py     per-domain settings (LLM endpoint/key/model + rate-limit/retry/timeout/budget)
  rag/config.py        per-domain settings (embedding model)
  notification/        incident alerts (router, service, models, schemas, sse, constants)
  streaming/           per-bus live signal SSE (manager, router)
  persistence/         FaultTicket → Postgres (models, service, schemas, router → GET /tickets)
  rag/                 SOP knowledge base (kb_loader, retriever, vector_store)  [support lib]
  simulation/          EMPTY — scada_sim/relay_sim deleted and waveform.py moved
                       to backend/kafka/; the package itself can go
  kafka/               event infra: topics, producer, consumer, admin (topic mgmt), workers, handlers/
                       waveform.py — the raw.signals FRAME (expand/rms/gate tests), beside the
                       RawSignal schema in schemas.py that it implements
  alembic/ + alembic.ini   migrations

ml/        TOP-LEVEL package, a sibling of backend/ — not backend/ml/:
  fault_detector.py    PRIMARY detection — testbed event IsolationForest (per-bus feature rows)
  fault_classifier.py  supervised RandomForest — fault type / category / location
  feature_extractor.py raw 3-phase → event row bridge (1-cycle DFT); driven live by backend/kafka/handlers/extract.py
  attribution.py       why a row scored anomalous (feature deltas vs the normal baseline)
  NOTE: these resolve the repo root by finding pyproject.toml, NOT by counting
  parents — a hard-coded depth broke silently when the package moved.

docker/    Dockerfile + entrypoint.sh (waits for infra → migrate → build KB → uvicorn)
scripts/   15 files. bootstrap.py (topics+models+KB), produce_waveforms.py (LIVE driver), produce_events.py (offline replay), refresh_kb.py, reproduce_steps_1_4.py + reproduce_step{4,5,6,7}*.py (paper reproduction), generate_normal_data.py, analyze_testbed.py, validate_isoforest.py, llm_smoke_test.py, load_testbed.py
           NOTE: load_testbed.py is NOT a standalone script — ml/fault_detector.py and
           ml/fault_classifier.py import it, which is why the Docker build context is the repo root
data/      sop/ (SOP .md)  synthetic/ (LEGACY, deprecating)  generated/ (normal_train, validation)  testbed/ (LARGE — see rules)
docs/      System_Architecture.md (authoritative), API_Reference.md, Agent_Architecture.md, Knowledge_Base_Index.md
frontend/  React operator console (Vite + React 19 + Tailwind v4 + shadcn/Radix, TanStack Query, Zustand).
           features/{incidents,map,overview,assignments}/ · shared/ · app/{routes,layouts,store}
           Map stack: MapLibre GL + react-map-gl + pmtiles, with a SELF-HOSTED offline
           Jamaica basemap in public/map/ (see frontend/README.md — do not delete those
           assets, they are the basemap). Overview is the LANDING page at
           /overview, and `/` REDIRECTS to it rather than mounting Overview
           twice — one canonical URL per page keeps the sidebar's active state
           honest (nav-main matches on prefix). It was briefly a bottom drawer
           on the map, which stacked a thing you read on a thing you operate.
           Incidents is the map screen at /incidents, with
           /incidents/:incidentId opening a pin's panel.
           features/assignments/ is the ticket-ownership page at /assignments —
           a filterable table + a route-driven detail sheet
           (/assignments/:incidentId). There was a dnd-kit kanban board beside
           the table; it was REMOVED, along with the view toggle and the
           @dnd-kit/core dependency. Don't reintroduce one without asking.
           AssignmentDetailPanel (Work/Diagnosis/Activity) is SHARED: the map's
           incident panel renders the same component, so a ticket's detail is
           defined in one place. Its defaultTab differs by page on purpose —
           Work on /assignments, Diagnosis on the map. It fetches by incident id
           and takes its height from its parent — don't give it
           viewport-relative sizing or a second copy.
backend/tests/ test_api.py (AsyncClient+ASGITransport), test_assignments.py (routes + real-DB integration), test_feature_extractor.py, test_fault_ticket_schema.py, test_health.py
```

---

## Best practices to follow

Source: **https://github.com/zhanymkanov/fastapi-best-practices** (its `README.md` and `AGENTS.md`). Key rules, adapted to this repo (`backend/` instead of `src/`):

- **Domain structure.** Each domain package holds `router.py`, `schemas.py` (Pydantic), `models.py` (ORM), `service.py` (business logic), `dependencies.py`, `constants.py`, `config.py`, `exceptions.py`, `utils.py`. Keep routers thin; logic lives in `service.py`. Import with top-level module names (`from backend.faults import service as faults_service`) — no deep cross-domain or wildcard imports.
- **Async correctness.** Never run blocking I/O (`requests`, `time.sleep`, sync DB, `open()`) inside `async def` — it freezes the event loop. Use `async def` + `await` for I/O; wrap blocking/sync SDK calls in `asyncio.to_thread` / `run_in_threadpool`; offload CPU-bound work (>50ms) to a worker. (The Kafka handlers already `to_thread` the LLM + sklearn calls.)
- **Dependencies.** Use the `Annotated[T, Depends(...)]` form, not default-arg `Depends()`. Validate inside dependencies; chain them for reuse.
- **Pydantic.** Use built-in validators / `Field` constraints / `StrEnum`; don't mix `Field(ge=…, default=None)`; use `@field_serializer` (not `json_encoders`). **One `BaseSettings` per domain** (see TODO — we currently centralize).
- **Routes.** Always set `response_model`, `status_code`, `tags`, `summary`/`description`. Hide docs outside dev.
- **Database.** SQLAlchemy 2.0 async (`AsyncConnection`); tables lowercase snake_case singular; consistent FK names; explicit MetaData naming convention (already in `backend/constants.py`); SQL-first (joins/aggregation in DB).
- **Migrations.** Alembic owns the schema (`alembic -c backend/alembic.ini upgrade head`). Migrations static + reversible; filenames `YYYY-MM-DD_slug.py` (configured). Don't use `create_all` in app startup.
- **Tests.** `httpx.AsyncClient` + `ASGITransport`; override deps via `app.dependency_overrides`; real DB in integration tests (don't mock the DB).
- **Lint/format.** Ruff (`ruff check --fix` / `ruff format`) — config in `pyproject.toml`.
- **Auth note:** this project intentionally has **no auth/users** (operator dashboard). SSE is broadcast (notifications) or per-bus (streaming). Do not reintroduce per-user auth.

---

## Project-specific conventions

- **Models:** coordinator → `LLM_ENDPOINT` / `LLM_API_KEY` / `LLM_MODEL` (**Google AI Studio `gemini-3.8-flash`** by default); embeddings → local `bge-small` (offline). `AZURE_OPENAI_*` still works as aliases. If the key is unset/placeholder, `run_fault_diagnosis` returns a **local heuristic ticket** (no LLM) — intentional, keep it working.
- **TWO clients, one config (`agent.build_chat_model`).** `LLM_PROVIDER` (`auto`|`google`|`openai`) selects; `auto` picks Google when the endpoint is `generativelanguage.googleapis.com`. **Google MUST use the native client** — Gemini 3.x attaches an opaque `thought_signature` to every function call and requires it echoed back with the tool result, and the OpenAI chat-completions format has no field to carry it. A single call over the compat layer succeeds; the coordinator's ReAct loop fails on turn 2 with `400 ... missing a thought_signature ... position 2`. Gemini 2.x predates the requirement but is closed to new API projects. **Do not "simplify" this back to one `ChatOpenAI`.** Everything else (Azure, OpenRouter, Groq, vLLM, Ollama) stays on the OpenAI path.
- **Both the app and `scripts/llm_smoke_test.py` build their client through `build_chat_model`.** The smoke test used to construct its own `ChatOpenAI`, so after the coordinator moved to the native client it silently kept testing the old one and reported PASS on a setup that could not work. A test that builds its own subject is not testing the app.
- **LLM replies are not always strings.** `ChatGoogleGenerativeAI` returns a LIST of content blocks; `ChatOpenAI` returns a `str`. `str(a_list)` yields a Python repr, so JSON extraction finds braces and parses garbage — and the coordinator falls back to a heuristic ticket with no error. Normalise through `backend.utils.message_text`.
- **The pipeline pins what it knows (`_pin_server_facts`).** The LLM fills the whole schema whether or not it has grounds to, so `ticket_id`, `severity`, `scenario`, `bus_id`, `created_at` and the evidence window are overwritten from the detection payload after validation. Observed: one ticket id (`TICK-IEEE13-001`) on every incident, a 2026 fault dated 2023, and a bus choice that moved `customers_affected` from 6,400 to 980. `fault_type`, `summary`, `root_cause` and `recommended_actions` stay the model's.
- **Detection-as-trigger:** the coordinator never calls a detection tool; it diagnoses the `anomalies.detected` payload (`feeder`, `verdict`, `topBuses`) and only calls `kb_retrieve`.
- **Idempotency:** `incident_id` keys the ticket; persistence upserts (at-least-once Kafka delivery → overwrite, not duplicate).
- **Never put operator state on `fault_tickets`.** `upsert_ticket` rewrites every column on each redelivery, so assignment/work state stored there is silently reset. It belongs in `ticket_assignments`, which no Kafka handler writes; reads LEFT JOIN, so a missing row *means* unassigned. `backend/tests/test_assignments.py::test_assignment_survives_ticket_redelivery` pins this.
- **Two status concepts.** `FaultTicket.status` (diagnosed/acknowledged/resolved) is LLM-produced and pipeline-owned. `TicketAssignment.work_state` (unassigned → assigned → in_progress → blocked → resolved → closed) is the operator's. Do not merge them.
- **Kafka:** six consumer groups for fan-out (`extraction`, `detection`, `streaming`, `coordinator`, `notification`, `persistence`); `run_consumer(group_id, handlers)` is generic. `extraction` and `streaming` both read `raw.signals` on the batched fast consumer (at-most-once: a dropped frame costs samples, not a ticket).
- **The extraction trigger is latched in the handler**, not in `FeatureExtractor.cut_window()` — that fires at "now", so its window always ends `window_seconds` in the future, which a live worker can never wait out. Use `window_around(t_fire)` for streaming.
- **`FeatureExtractor.ingest` is on the hot path** (~1.9k samples/s per bus). Buffers are deques pruned from the front; rebuilding the list per sample measured 3.5k samples/s total, which could not sustain two buses live. Partition by `feeder`/`bus_id`/`incident_id`.
- **Embedding dim change requires a KB rebuild** (`scripts/refresh_kb.py`).
- **SOP-005..012 are SYNTHETIC references**, generated from standard protection practice and marked as such in their own body text. Not approved utility procedures — don't describe them as JPS's.
- **Query the KB with descriptions, not codes.** `FAULT_QUERY_TERMS` (`backend/faults/constants.py`) expands `SLG`/`LL`/`OPEN_1PH`... before retrieval; a bare code retrieves the wrong SOP. Phrase terms positively — negations like "no ground path" embed as their own opposite. Adding a classifier label without adding query terms is caught by `backend/tests/test_kb_retrieval.py`.
- **Ticket citations are re-verified**, not trusted: `_restore_citation_snippets` replaces LLM-written snippets with the real KB text by `source_id` and drops unknown ids.

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
uv sync                                                # deps from uv.lock, exact versions
alembic -c backend/alembic.ini upgrade head                # create schema (Alembic owns it)
.venv/Scripts/python.exe scripts/bootstrap.py          # topics + models + Chroma KB
# set AZURE_OPENAI_* in .env (else the coordinator returns a heuristic ticket)
uvicorn backend.api.main:app --reload                      # API + 6 consumer groups; /ready checks DB+Kafka
.venv/Scripts/python.exe scripts/produce_events.py     # drives detection → coordinator → tickets
```
Don't run the host `uvicorn` and the container `app` at once — same Kafka `group.id`s + a port-8000 clash.
Gotcha: the container DB is published on **`:5433`**, not `:5432`, so a native host Postgres can't shadow it. Host clients use `localhost:5433` (the `backend/config.py` defaults and `.env.example` match); the app-in-container uses `db:5432`. A host client pointed at 5432 may silently reach a different database, and the real-DB tests skip rather than fail when nothing answers.

---

## TODO — near-term

**Recently closed:**
- [x] **Feature-extraction worker** — the `extraction` consumer group on `raw.signals` (`backend/kafka/handlers/extract.py`). Open decisions A and B are resolved: `raw.signals` carries 3-phase waveform frames, and the live chart plots per-cycle RMS.

**Deprecations (planned):**
- [x] **`ml/baseline_detector.py` is GONE**, with `scripts/run_detection_demo.py` and `ml/models/baseline_isolation_forest.pkl`. `fault_detector` (event path) is the only detection path.
- [x] **The old synthetic data/DB is GONE** (`data/synthetic/*`, `synthetic_signals.db`).
- [x] **The legacy demo chain is GONE** — `produce_signals.py`, `run_full_demo_with_latency.py`, `make_ticket_from_demo.py`, `save_demo_signals.py`, `signal_writer.py`, `generate_synthetic_data.py` and `load_to_sqlite.py` are all deleted. scripts/ is down from 26 files to 19.

**Other gaps:**
- [x] **Bus namespaces are reconciled.** `produce_signals.py` was the last thing emitting `bus_1/2/3`, and it is deleted. Everything now flows IEEE13 ids (`b632/b650/b671/b675/b684`) from `raw.signals` through `feeder.events` to the ticket, so a ticket and its live chart join. It was retired rather than renamed, which is what the old note asked for.
- [ ] **Notification email/external channels** — only in-process SSE broadcast exists; no email/SMS/webhook delivery.
- [ ] **Feeder-agnostic classifier** — `fault_classifier` is feeder-specific (13-bus columns); §6.1 wants topology-independent aggregate features so it transfers to new feeders.

**Done (for reference):** **concurrency isolation** (`backend/kafka/executors.py` — dedicated Kafka thread pool + ML `ProcessPoolExecutor`; fixed the live chart freezing while events processed) · **fast-path streaming consumer** (batched auto-commit for `raw.signals`; at-most-once for that topic only) · **React operator console** (`frontend/` — map-first incidents screen) · event/`fault_detector` detection · supervised `fault_classifier` (type/category/location, attached to `anomalies.detected`) · coordinator (OpenAI-compatible LLM + `kb_retrieve`, rate-limited + bounded retries, heuristic fallback) · per-domain configs · `StrEnum` `FaultTicket` · `feature_extractor` DSP (1-cycle DFT) · DLQ on all topics · `GET /tickets` + `/tickets/{id}` history API · `/ready` (DB+Kafka) · Alembic migration · Kafka topic bootstrap · Dockerfile + self-bootstrapping entrypoint · integration tests.