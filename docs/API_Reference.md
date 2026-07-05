# API Reference — Multi-Agent Fault Detection (MAFD)

FastAPI endpoints exposed by `app.api.main`. The authoritative system design is
`docs/System_Architecture.md`; most work flows through Kafka, not HTTP, so this
surface is intentionally small.

Base app: `uvicorn app.api.main:app`. Interactive docs at `/docs`.

---

## GET /health
Liveness check.

**Response** `200`
```json
{"status": "ok"}
```

---

## POST /faults/diagnose
Run the coordinator (SOP retrieval + LLM, or the offline heuristic fallback) on a
**detection result** and return a validated `FaultTicket`. Detection runs upstream
(the event IsolationForest) — this endpoint diagnoses its output (detection-as-trigger).

**Request** (`DiagnoseRequest`)
```json
{
  "feeder": "ieee13",
  "incident_id": "ieee13:evt_001",
  "severity": "high",
  "anomaly_score": 0.12,
  "top_buses": [
    {"bus": "b671", "minVa": 0.42, "maxIa": 4200.0, "maxI0I1": 0.31, "maxI2I1": 0.05}
  ]
}
```

**Response** `200` — `FaultTicket` (`response_model`): `ticket_id`, `scenario`,
`bus_id`, `fault_type`, `severity` (`low|medium|high`), `status`, `summary`,
`root_cause`, `recommended_actions[]`, `evidence[]`, `kb_citations[]`, `created_at`.

---

## GET /notifications
List recent operator notifications (Postgres).

**Response** `200` — `NotificationListResponse` `{ "items": [...], "unread_count": n }`.

## POST /notifications/read-all
Mark all notifications read. **Response** `204`.

## GET /notifications/stream
**SSE** stream of incident alerts, broadcast to every connected dashboard (no auth,
no per-user scoping). `text/event-stream`; heartbeat every ~15 s.

---

## GET /stream/signals?bus_id=<bus>
**SSE** live per-bus signal feed for the UI chart. On connect the client receives a
snapshot of the bus's rolling buffer (~5 min), then live readings. `text/event-stream`.

---

## Notes
- **No authentication** — MAFD is an operator dashboard; streams are broadcast
  (notifications) or per-bus (signals).
- Tables are owned by Alembic: `alembic -c app/alembic.ini upgrade head`.
- The Kafka consumer workers start with the app lifespan when `KAFKA_ENABLED=true`.
