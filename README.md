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
                                                   │   Azure gpt-4o-mini + kb_retrieve (RAG)  ·  offline heuristic fallback
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
OpenAI `gpt-4o-mini` (coordinator LLM) · local `bge-small` embeddings + Chroma
(RAG) · scikit-learn (detection/classification) · Streamlit (legacy ticket browser).

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
scripts/             produce_events / produce_signals / bootstrap / refresh_kb / generate_* / validate_*
ui/streamlit_app.py  legacy ticket browser (reads ticket JSON; not SSE-wired yet)
tests/               pytest suite (AsyncClient + ASGITransport)
```

## Running

Full stack (Postgres + Kafka + Kafdrop + app) in Docker — see **`README.docker.md`**
for details and the app-on-host variant:

```bash
docker compose -f docker-compose.dev.yaml up -d --build   # app :8000 · kafdrop :9000
.venv/Scripts/python.exe scripts/produce_events.py        # drive detection → coordinator → tickets
curl -fsS http://localhost:8000/ready
```

Without `AZURE_OPENAI_*` configured, the Coordinator returns a **local heuristic
ticket** (no LLM call) — intentional, so the pipeline runs end-to-end offline.

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
.venv/Scripts/python.exe -m pytest -q
```

`httpx.AsyncClient` + `ASGITransport` (no broker/DB needed), dependency overrides,
and the feature-extraction DSP unit tests. Coverage summary + gaps:
`docs/Testing_Report.md`.

## Streamlit UI

```bash
.venv/Scripts/python.exe -m streamlit run ui/streamlit_app.py   #  →  http://localhost:8501
```

Note: the current UI is a **legacy ticket browser** that reads ticket JSON files and
is **not yet wired to the SSE streams**. Connecting it to `/notifications/stream` and
`/stream/signals` is a near-term TODO (architecture doc §16).

## Status & next

The event-driven backend runs end-to-end on real infra (Docker Postgres + Kafka).
Near-term work (see `docs/System_Architecture.md` §16 and `AGENTS.md`):

1. **Feature-extraction worker** — the 6th consumer group on `raw.signals` (blocked
   on the `raw.signals` → 3-phase-waveform schema decision).
2. Deprecate the legacy time-series path (`baseline_detector.py` + old synthetic data).
3. Fast-path streaming consumer for the `raw.signals` firehose.
4. Feeder-agnostic classifier (transfers across feeders).
5. Wire the Streamlit UI to SSE; add external notification channels.
