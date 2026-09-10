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
| `tests/test_waveform_pipeline.py` | 11 tests | **The live bridge.** The `raw.signals` wire format (expand / RMS / sag gate); the extraction worker with the producer faked; and the CHAIN TEST — waveform samples driven through the real extractor, detector, classifier and coordinator, asserting a valid `FaultTicket` emerges. That last one is the first test to prove a signal can become a ticket |
| `tests/test_kb_retrieval.py` | 16 tests | **SOP retrieval.** One SOP per fault type against the built vector store, the query-expansion contract, provenance survival, and citation re-verification. Skips when `artifacts/kb` is absent |
| `tests/test_assignments.py` | 18 tests | **Assignments.** Unit: severity → priority/SLA defaults (synonyms included), and the LEFT JOIN projection that makes a missing assignment row read as `unassigned`. Routes: list with a dependency override, `409` on a stale `expected_version`, `404` on an unknown incident, `422` on an unknown field. **Integration against a real Postgres** (skipped when the dev DB isn't listening): the redelivery invariant, implied state transitions, unassignment, explicit-state precedence, no-op patches not bumping the version, open-count excluding terminal work, and comments not silently claiming a ticket. Three of these are review regressions: the priority filter must match the *derived* priority of tickets with no assignment row, an operator override must beat that default, and two concurrent first-writes must not both win |
| `tests/test_fault_ticket_schema.py` | `test_fault_ticket_instantiation` | `FaultTicket` / `EvidenceWindow` / `KBCitation` validation |
| `tests/test_health.py` | `test_health_endpoint` | `/health` via `TestClient` |

The one to keep: **`test_assignment_survives_ticket_redelivery`**. It assigns a
ticket, re-runs `upsert_ticket` for the same incident (what Kafka's at-least-once
delivery does on a rebalance, restart or DLQ replay), and asserts the diagnosis
was rewritten while the assignment was not. If that ever fails, operator state
has leaked onto `fault_tickets` and a redelivery is silently discarding work.

It is also the first test in the suite that talks to a real database, per the
project's rule about not mocking the DB. It skips itself when nothing is
listening on the configured Postgres port, so the suite still passes offline —
at the cost that a green run doesn't prove the integration tests ran. Check for
`skipped` in the pytest summary when it matters.

## Not yet covered (gaps)

- **Kafka handlers / consumer** (`detect`, `diagnose`, `notify`, `persist`, `stream`,
  `run_consumer`, DLQ routing) — no integration test against a real or embedded broker.
- **Persistence** — the `GET /tickets` history API is untested. `upsert_ticket`
  idempotency is now covered indirectly by the assignment redelivery test, but
  not on its own terms.
- **Detector / classifier scoring** — no test asserts `detect_event` /
  `classify_event` behavior (including the non-finite input guard).
- **RAG retrieval** — now covered by `tests/test_kb_retrieval.py` (16 tests): one
  SOP asserted per fault type, operational SOPs not displaced, provenance present,
  and LLM-written citations replaced with authoritative KB text. The graceful
  degradation `[]` path is still unverified.
- **SSE** — `/notifications/stream` and `/stream/signals` snapshot-then-live behavior.
- **Assignment concurrency under real contention** — the `409` path is tested
  sequentially; two genuinely simultaneous writers racing the `SELECT … FOR
  UPDATE` are not.
- **Front end** — `frontend/` has its own vitest suite (`pnpm test`, 46 tests
  including the assignment SLA/age helpers, the implied-state mirror of the
  server rule, and the activity feed's prose); it is not part of the pytest run.
- **Drag-and-drop** — the board's dnd-kit interactions are verified by hand, not
  by test. The state dropdown in the table is the same code path and is the
  keyboard-accessible route, so the untested part is the gesture, not the write.

These are the highest-value additions for the next testing pass.
