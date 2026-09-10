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

## GET /operators
The operator roster, with each operator's current open-ticket count.

**Query**: `include_inactive` (default `false`).

**Response** `200` — `OperatorListResponse` `{ "items": [...], "count": n }`. Each
item: `id`, `name`, `initials`, `role`, `parish`, `capacity`, `on_shift`,
`active`, `created_at`, `open_count`.

> Operators are **roster entries, not user accounts** — MAFD has no auth, so
> there are no credentials here. See the note at the foot of this file.

## POST /operators
Add a roster entry. **Response** `201` — `Operator`.

## PATCH /operators/{operator_id}
Update a roster entry (partial). **Response** `200` — `Operator`.

---

## GET /assignments
Fault tickets joined to their assignment row — the Assignments page's one read.

**Query**: `work_state`, `assignee_id`, `unassigned` (bool), `severity`
(`low|medium|high`), `priority` (`p1..p4`), `q` (substring over bus / fault /
summary / ids), `limit` (1-500, default 100), `offset`.

**Response** `200` — `AssignmentListResponse`. Each item carries the ticket
projection (`incident_id`, `ticket_id`, `bus_id`, `fault_type`, `severity`,
`status`, `summary`, `created_at`) plus the assignment (`work_state`,
`priority`, `assignee_id`, `assignee_name`, `assignee_initials`, `due_at`,
`note`, `version`, `updated_at`).

> A ticket with no assignment row yet is returned as `work_state: "unassigned"`,
> `version: 0` and a severity-derived `priority` — the row is created lazily on
> the first write, so the client never special-cases a missing one.

## GET /assignments/{incident_id}
One ticket's assignment. **Response** `200` — `Assignment`, `404` if unknown.

## PATCH /assignments/{incident_id}
Assign, unassign, or change work state / priority / due date / note.

**Request** (`AssignmentUpdate`, all fields optional, unknown fields rejected)
```json
{"assignee_id": "01J8...", "work_state": "in_progress", "expected_version": 3}
```

`assignee_id: null` unassigns. Assigning a previously untouched ticket also moves
it to `assigned` unless the same request sets `work_state` explicitly.

**Header**: `X-Actor-Id` — the operator performing the action, recorded on the
activity event. Not authenticated (see the note below).

**Response** `200` — `Assignment` · `404` unknown incident · **`409`** when
`expected_version` no longer matches: someone else changed the ticket first, and
the write was refused rather than silently overwriting theirs.

## POST /assignments/{incident_id}/comments
Append a comment to the activity feed. Does **not** create or claim the
assignment. **Request** `{"body": "..."}` · **Response** `201` — `AssignmentEvent`.

## GET /assignments/{incident_id}/events
The activity feed, oldest first — state changes, reassignments and comments in
one chronological list. **Response** `200` — `AssignmentEventListResponse`.

---

## Notes
- **No authentication** — MAFD is an operator dashboard; streams are broadcast
  (notifications) or per-bus (signals).
- **`X-Actor-Id` is a claim, not a credential.** Operators are roster rows with
  no password or session, and the console sends whichever id it is "acting as".
  The activity log is therefore **attributed, not authenticated** — anyone at the
  terminal can act as anyone. That is the right size for a shared control-room
  terminal and is *not* an audit trail; real identity would be SSO against the
  utility's directory.
- Tables are owned by Alembic: `alembic -c app/alembic.ini upgrade head`.
- The Kafka consumer workers start with the app lifespan when `KAFKA_ENABLED=true`.
