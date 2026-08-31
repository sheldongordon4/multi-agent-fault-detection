# Multi-Agent Fault Detection (MAFD)

MAFD is a **fault detection, classification, and diagnosis** system for electrical
power **distribution feeders**. It ingests grid signals, detects disturbances,
classifies the fault, retrieves the relevant **Standard Operating Procedure (SOP)**,
and produces an explainable **FaultTicket** for operators. It is an **event-driven
pipeline** of decoupled services connected by **Kafka**.

> **Docs.** `docs/System_Architecture.md` is authoritative (target design + as-built
> status §16 + open decisions §14). `AGENTS.md` is the working summary for
> contributors. This README is the orientation / quick-start.

## Architecture (as-built)

```
scripts/produce_events.py ─▶ feeder.events ─▶ [detection]  app/ml/fault_detector (IsolationForest)
                                                   │   + app/ml/fault_classifier (RandomForest: type/category/location)
                                                   │  publishes verdict + most-disturbed buses + classification
                                                   ▼
                                             anomalies.detected ─▶ [coordinator]  app/faults
                                                   │   Azure gpt-5.4-mini + kb_retrieve (RAG)  ·  offline heuristic fallback
                                                   ▼
                                             faulttickets ─┬─▶ [notification]  SSE broadcast + Postgres
                                                           └─▶ [persistence]   Postgres (upsert) → GET /tickets

scripts/produce_signals.py ─▶ raw.signals ─▶ [streaming]  per-bus rolling buffer ─▶ SSE chart
```

**Detection-as-trigger:** detection runs *upstream*; the Coordinator does not run
detection — it diagnoses the `anomalies.detected` payload and its only LLM tool is
`kb_retrieve`. Five Kafka consumer groups (detection, streaming, coordinator,
notification, persistence) give the fan-out; any handler that keeps failing routes
the message to a `<topic>.dlq` dead-letter topic.

**The one stubbed link:** the live `raw.signals → feeder.events` feature-extraction
worker isn't wired to Kafka yet — today `produce_events.py` replays pre-reduced event
rows onto `feeder.events` directly. The DSP that would feed it
(`app/ml/feature_extractor.py`) is implemented and unit-tested. See §16 of the
architecture doc.

## Tech stack

Python 3.11+ · FastAPI · Pydantic v2 · SQLAlchemy 2.0 async + asyncpg + Alembic →
Postgres · confluent-kafka (+ Kafdrop) · LangChain / LangGraph ReAct agent · Azure
OpenAI `gpt-5.4-mini` (coordinator LLM) · local `bge-small` embeddings + Chroma
(RAG) · scikit-learn (detection/classification) · **React 19 + Vite + Tailwind v4 +
MapLibre GL** (operator console) · Streamlit (legacy ticket browser).

## Repo layout

```
app/
  api/main.py        FastAPI app + lifespan (starts Kafka workers), /health, /ready
  faults/            COORDINATOR domain (agent, service, tools, schemas, config)
  ml/                fault_detector · fault_classifier · feature_extractor · baseline_detector (deprecated)
  rag/               SOP knowledge base (kb_loader, vector_store, retriever)
  kafka/             topics, producer, consumer, admin, workers, handlers/
  notification/ streaming/ persistence/   the three fan-out services (+ SSE)
  alembic/           migrations (Alembic owns the schema)
docs/                System_Architecture.md (authoritative), Agent_Architecture.md, API_Reference.md, ...
data/sop/            SOP .md knowledge base       data/testbed/ + data/generated/  ML data
scripts/             reproduce_step{1..7}.py  ·  reproduce_steps_1_4.py  ·  produce_events / produce_signals
                     bootstrap / refresh_kb / generate_* / validate_*
frontend/            React operator console — map-first incidents screen (see frontend/README.md)
ui/streamlit_app.py  legacy ticket browser (reads ticket JSON; not SSE-wired yet)
tests/               pytest suite (AsyncClient + ASGITransport)
```

## Reproduction flow

The Git-tracked reproduction runners are:

1. `scripts/reproduce_steps_1_4.py` — combined data-generation, detection,
   classification, and latency workflow.
2. `scripts/reproduce_step5_noise_sensitivity.py`
3. `scripts/reproduce_step6_rag_retrieval.py`
4. `scripts/reproduce_step7_faithfulness.py`

Run the combined workflow with:

```bash
python scripts/reproduce_steps_1_4.py
```

Generated datasets and artifacts are intentionally excluded from Git and are
created by the reproduction runners.

## Running

Full stack (Postgres + Kafka + Kafdrop + app + React client) in Docker — see **`README.docker.md`**
for details and the app-on-host variant:

```bash
docker compose -f docker-compose.dev.yaml up -d --build   # app :8000 · kafdrop :9000
.venv/bin/python scripts/produce_events.py                # drive detection → coordinator → tickets
curl -fsS http://localhost:8000/ready
```

Without `AZURE_OPENAI_*` configured, the Coordinator returns a **local heuristic
ticket** (no LLM call) — intentional, so the backend pipeline runs offline.

The Docker stack also starts the React operator client at `http://localhost:5173`.

## HTTP API

Small surface — most work flows through Kafka. Full details in `docs/API_Reference.md`.

| Method & path | Purpose |
| ------------- | ------- |
| `GET /health` · `GET /ready` | liveness · readiness (checks Postgres + Kafka) |
| `POST /faults/diagnose` | run the Coordinator on a detection result → `FaultTicket` |
| `GET /tickets` · `GET /tickets/{incident_id}` | fault-ticket history (Postgres) |
| `GET /notifications` · `POST /notifications/read-all` | operator notifications |
| `GET /notifications/stream` | SSE incident alerts (broadcast) |
| `GET /stream/signals?bus_id=<bus>` | SSE per-bus live signal feed (snapshot + live) |

Interactive docs at `/docs`.

## Testing

```bash
.venv/bin/python -m pytest -q
```

`httpx.AsyncClient` + `ASGITransport` (no broker/DB needed), dependency overrides,
and the feature-extraction DSP unit tests. Coverage summary + gaps:
`docs/Testing_Report.md`.

## UI

**Operator console (`frontend/`)** — the real UI. Runs as the `client` service in
`docker-compose.dev.yaml` (→ http://localhost:5173) or `pnpm dev` in `frontend/`.

One map-first screen: a full-bleed **offline** Jamaica basemap with substation
markers, IEEE13 feeder topology and parish fault shading; a collapsible incident
list; a detail panel; and the overview (stat tiles, live signal, fault types) as a
three-detent bottom drawer. The basemap is self-hosted with no API keys and no
runtime third-party calls — see **`frontend/README.md`** for the assets, how to
regenerate them, and the licensing.

**Streamlit (legacy)**

```bash
.venv/bin/python -m streamlit run ui/streamlit_app.py            #  →  http://localhost:8501
```

A **legacy ticket browser** that reads ticket JSON files and is **not** wired to the
SSE streams. Superseded by the React console for day-to-day use.

## Status & next

The event-driven backend runs end-to-end on real infra (Docker Postgres + Kafka).
Near-term work (see `docs/System_Architecture.md` §16 and `AGENTS.md`):

1. **Feature-extraction worker** — the 6th consumer group on `raw.signals` (blocked
   on the `raw.signals` → 3-phase-waveform schema decision).
2. Deprecate the legacy time-series path (`baseline_detector.py` + old synthetic data).
3. Feeder-agnostic classifier (transfers across feeders).
4. External notification channels (email/webhook) beyond in-process SSE.
5. **Reconcile the bus namespaces** — streaming uses `bus_1/2/3`, tickets carry
   IEEE13 ids (`b6xx`), so nothing joins them. A symptom of (1), not a rename.

Recently landed: **concurrency isolation** (dedicated Kafka thread pool + ML process
pool — the live signal chart no longer freezes while events process), the
**fast-path `raw.signals` consumer**, and the **React operator console**.
