# Testing Report — MAFD

What the automated suite covers today. Run it with:

```bash
.venv/bin/python -m pytest -q
```

`pyproject.toml` sets `asyncio_mode = "auto"`, so `async def` tests run without a
per-test marker. Tests use `httpx.AsyncClient` + `ASGITransport` (which does **not**
start the app lifespan, so no broker/DB is required) with `dependency_overrides` and
monkeypatched services for external I/O.

## Suite

| File | Tests | Covers |
| ---- | ----- | ------ |
| `tests/test_api.py` | `test_health`, `test_diagnose_returns_fault_ticket`, `test_notifications_list_with_dependency_override` | `/health`; `POST /faults/diagnose` returns a `FaultTicket` (diagnosis monkeypatched); `GET /notifications` with a DB dependency override |
| `tests/test_feature_extractor.py` | `test_dft_phasor_recovers_amplitude_and_phase`, `test_phasors_on_balanced_window`, `test_reduced_features_are_finite` | the DSP: single-bin DFT recovers a known amplitude/phase; per-cycle phasors on a balanced 3-phase window; reduced features are always finite (the §11 de-energized-bus guard) |
| `tests/test_fault_ticket_schema.py` | `test_fault_ticket_instantiation` | `FaultTicket` / `EvidenceWindow` / `KBCitation` validation |
| `tests/test_health.py` | `test_health_endpoint` | `/health` via `TestClient` |

## Not yet covered (gaps)

- **Kafka handlers / consumer** (`detect`, `diagnose`, `notify`, `persist`, `stream`,
  `run_consumer`, DLQ routing) — no integration test against a real or embedded broker.
- **Persistence** — `upsert_ticket` idempotency and the `GET /tickets` history API
  are untested (best-practice is a real DB in integration tests).
- **Detector / classifier scoring** — no test asserts `detect_event` /
  `classify_event` behavior (including the non-finite input guard).
- **RAG retrieval** — `kb_retrieve` end-to-end (embeddings + Chroma) is untested;
  its graceful-degradation `[]` path is likewise unverified.
- **SSE** — `/notifications/stream` and `/stream/signals` snapshot-then-live behavior.

These are the highest-value additions for the next testing pass.
