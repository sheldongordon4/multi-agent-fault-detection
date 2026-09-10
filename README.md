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
scripts/produce_waveforms.py ─▶ raw.signals ─▶ [extraction]  app/kafka/handlers/extract
                                                   │   FeatureExtractor: 1-cycle DFT → reduced event row
                                                   ▼
                                             feeder.events ─▶ [detection]  app/ml/fault_detector (IsolationForest)
                                                   │   + app/ml/fault_classifier (RandomForest: type/category/location)
                                                   │  publishes verdict + most-disturbed buses + classification
                                                   ▼
                                             anomalies.detected ─▶ [coordinator]  app/faults
                                                   │   Gemini via kb_retrieve (RAG)  ·  offline heuristic fallback
                                                   ▼
                                             faulttickets ─┬─▶ [notification]  SSE broadcast + Postgres
                                                           └─▶ [persistence]   Postgres (upsert) → GET /tickets

                     raw.signals ─▶ [streaming]  per-cycle RMS ─▶ SSE chart
```

**Detection-as-trigger:** detection runs *upstream*; the Coordinator does not run
detection — it diagnoses the `anomalies.detected` payload and its only LLM tool is
`kb_retrieve`. Six Kafka consumer groups (extraction, detection, streaming,
coordinator, notification, persistence) give the fan-out; any handler that keeps
failing routes the message to a `<topic>.dlq` dead-letter topic.

**`raw.signals` carries 3-phase waveform frames**, not scalar SCADA readings —
sequence ratios (I0/I1, I2/I1) need all three phases. One frame is one cycle for one
bus (`app/ml/waveform.py`); batching per cycle holds the topic at ~60 msg/s/bus
instead of ~2k. Both consumers read the frame through that one module, so the
detection view and the chart view cannot drift apart.

`scripts/produce_events.py` still replays pre-reduced rows straight onto
`feeder.events` for offline work — it bypasses extraction by design.

## Tech stack

Python 3.11+ · FastAPI · Pydantic v2 · SQLAlchemy 2.0 async + asyncpg + Alembic →
Postgres · confluent-kafka (+ Kafdrop) · LangChain / LangGraph ReAct agent · any
OpenAI-compatible LLM endpoint (Google AI Studio `gemini-3.8-flash` by default)
· local `bge-small` embeddings + Chroma
(RAG) · scikit-learn (detection/classification) · **React 19 + Vite + Tailwind v4 +
MapLibre GL** (operator console) · Streamlit (legacy ticket browser).

## Repo layout

```
app/
  api/main.py        FastAPI app + lifespan (starts Kafka workers), /health, /ready
  faults/            COORDINATOR domain (agent, service, tools, schemas, config)
  assignments/       ticket ownership: operator roster, work state, activity log
  ml/                fault_detector · fault_classifier · feature_extractor · waveform · baseline_detector (deprecated)
  rag/               SOP knowledge base (kb_loader, vector_store, retriever)
  kafka/             topics, producer, consumer, admin, workers, handlers/ (extract, detect, ...)
  notification/ streaming/ persistence/   the three fan-out services (+ SSE)
  alembic/           migrations (Alembic owns the schema)
docs/                System_Architecture.md (authoritative), Agent_Architecture.md, API_Reference.md, ...
data/sop/            SOP .md knowledge base       data/testbed/ + data/generated/  ML data
scripts/             reproduce_step{1..7}.py  ·  reproduce_steps_1_4.py  ·  produce_waveforms (live driver)
                     produce_events / produce_signals (offline replay)  ·  bootstrap / refresh_kb
                     generate_* / validate_*
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
.venv/bin/python scripts/produce_waveforms.py --fault SLG  # signals → extraction → ... → tickets
curl -fsS http://localhost:8000/ready
```

`produce_waveforms.py` drives the whole chain from `raw.signals`;
`produce_events.py` still exists to replay pre-reduced rows onto `feeder.events`
when you want to skip extraction.

Without `LLM_API_KEY` configured, the Coordinator returns a **local heuristic
ticket** (no LLM call) — intentional, so the backend pipeline runs offline. The
endpoint is provider-neutral: see `.env.example` for AI Studio, OpenRouter,
Azure and Ollama settings.

The Docker stack also starts the React operator client at `http://localhost:5173`.

## HTTP API

Small surface — most work flows through Kafka. Full details in `docs/API_Reference.md`.

| Method & path | Purpose |
| ------------- | ------- |
| `GET /health` · `GET /ready` | liveness · readiness (checks Postgres + Kafka) |
| `POST /faults/diagnose` | run the Coordinator on a detection result → `FaultTicket` |
| `GET /tickets` · `GET /tickets/{incident_id}` | fault-ticket history (Postgres) |
| `GET /assignments` · `PATCH /assignments/{incident_id}` | ticket ownership + work state |
| `GET /operators` | the operator roster (no accounts — see below) |
| `GET /notifications` · `POST /notifications/read-all` | operator notifications |
| `GET /notifications/stream` | SSE incident alerts (broadcast) |
| `GET /stream/signals?bus_id=<bus>` | SSE per-bus live signal feed (snapshot + live) |

Interactive docs at `/docs`.

## Testing

```bash
.venv/bin/python -m pytest -q
```

`httpx.AsyncClient` + `ASGITransport` (no broker/DB needed), dependency overrides,
the feature-extraction DSP unit tests, and the live chain — `tests/test_live_chain.py`
drives synthetic waveforms through the real extractor, detector and classifier and
asserts the fault that went in is the fault that comes out. Coverage summary + gaps:
`docs/Testing_Report.md`.

## UI

**Operator console (`frontend/`)** — the real UI. Runs as the `client` service in
`docker-compose.dev.yaml` (→ http://localhost:5173) or `pnpm dev` in `frontend/`.

Two screens. **Incidents** is map-first: a full-bleed **offline** Jamaica basemap with substation
markers, IEEE13 feeder topology and parish fault shading; a collapsible incident
list; and a detail panel. The overview (stat tiles, live signal, fault types) is
its own page at `/overview`. The basemap is self-hosted with no API keys and no
runtime third-party calls — see **`frontend/README.md`** for the assets, how to
regenerate them, and the licensing.

**Assignments** (`/assignments`) is where tickets get an owner. A filterable
**table** — the view that copes when a storm puts hundreds of tickets on it —
and a detail panel with three tabs: *Work* (assignee, state, priority, note),
*Diagnosis* (the coordinator's ticket) and *Activity* (an append-only log with
comments). **The map's incident panel is the same component**, so a fault can be
assigned without leaving the map (it opens on *Diagnosis* there, on *Work*
here).

Operators are a **roster, not user accounts**: MAFD has no auth, so the console
picks who it is "acting as" and the log is *attributed*, not *authenticated*.
Seed a starter roster with:

```bash
.venv/bin/python scripts/seed_operators.py
```

**Streamlit (legacy)**

```bash
.venv/bin/python -m streamlit run ui/streamlit_app.py            #  →  http://localhost:8501
```

A **legacy ticket browser** that reads ticket JSON files and is **not** wired to the
SSE streams. Superseded by the React console for day-to-day use.

## Status & next

The event-driven backend runs end-to-end on real infra (Docker Postgres + Kafka).
Near-term work (see `docs/System_Architecture.md` §16 and `AGENTS.md`):

1. Deprecate the legacy time-series path (`baseline_detector.py` + old synthetic
   data), and retire `produce_signals.py` with it — `produce_waveforms.py`
   supersedes it as the driver.
2. Feeder-agnostic classifier (transfers across feeders).
3. External notification channels (email/webhook) beyond in-process SSE.
4. **Finish the bus namespaces.** The live path now stamps IEEE13 ids (`b6xx`) on
   both halves, so a ticket and its chart finally join. Only the legacy
   `produce_signals.py` still emits `bus_1/2/3`, which (1) removes.

Recently landed: **the live bridge** (`raw.signals` waveform frames → `extraction`
consumer group → `feeder.events`, so a signal becomes a ticket with no replay script
in the middle), **ticket assignment** (`/assignments` — table, operator
roster, work state, activity log; kept off `fault_tickets` so Kafka redelivery
can't reset an operator's work), **concurrency isolation** (dedicated Kafka thread pool + ML process
pool — the live signal chart no longer freezes while events process), the
**fast-path `raw.signals` consumer**, and the **React operator console**.
