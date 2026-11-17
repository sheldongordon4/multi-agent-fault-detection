# API Reference — Multi-Agent Fault Detection (MAFD)

FastAPI endpoints exposed by `backend.api.main`. The authoritative system design is
`docs/System_Architecture.md`; most work flows through Kafka, not HTTP, so this
surface is intentionally small.

Base app: `uvicorn backend.api.main:app`. Interactive docs at `/docs`.

---

## GET /health
Liveness check.

**Response** `200`
```json
{"status": "ok"}
```

---

## GET /ready
Readiness — Postgres **and** Kafka are reachable. Each dependency is probed
independently (`SELECT 1` on the engine; Kafka `list_topics` with a 5 s timeout)
and reported by name, so a failing check says *which* one failed.

**Response** `200` when every check passes, **`503`** when any one does not. The
body has the same shape either way, so a load balancer can read the status code
while an operator reads the detail.
```json
{"ready": true, "checks": {"database": "ok", "kafka": "ok"}}
```
A failed check carries its error message, truncated to 160 characters:
```json
{"ready": false, "checks": {"database": "ok", "kafka": "error: ..."}}
```

> Liveness vs. readiness: `/health` says the process is up, `/ready` says it can
> do its job. The app deliberately **starts without Kafka** (the lifespan logs
> and continues), so `/health` alone would report a pipeline that cannot run.

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

## GET /tickets
Fault-ticket history from Postgres — what the persistence service wrote as
tickets came off the `faulttickets` topic.

**Query**: `limit` (1-500, default 50).

**Response** `200` — `TicketListResponse` `{ "items": [...], "count": n }`. Each
item is a `TicketSummary`: `incident_id`, `ticket_id`, `scenario`, `bus_id`,
`fault_type`, `severity`, `status`, `summary`, `created_at`, plus
`customers_affected` and `customers_share`.

> `customers_affected` / `customers_share` are **derived from `bus_id` on read**
> (`backend/persistence/service.py::_with_impact`), not stored columns — so the list
> can rank by impact without unpacking every ticket's `raw`, and a ticket
> diagnosed before the customer table existed still reports one.

---

## GET /tickets/repeat-offenders
Buses that have produced the **same fault code** more than once within a
trailing window — the "this one keeps coming back" view that a flat history
cannot show. Several SOPs turn on exactly this signal: repeated transient SLG at
one location precedes a permanent failure (`SOP-SLG-005`), and repeated lockouts
are an escalation trigger (`SOP-REC-012`).

**Query**: `days` (1-365, default 30), `min_occurrences` (2-50, default 2).

**Response** `200` — `RepeatOffenderResponse` `{ "items": [...], "count": n,
"window_days": d, "min_occurrences": m }` — the window is echoed back so a client
need not track what it asked for. Each item: `bus_id`, `fault_code`,
`occurrences`, `first_seen`, `last_seen`, `worst_severity`,
`customers_affected`, `mean_days_between`, `recent_incident_ids[]`.

> Declared **before** `/{incident_id}` in `backend/persistence/router.py`: FastAPI
> matches in declaration order, so the path parameter would otherwise capture
> `repeat-offenders` as an incident id and answer `404`.

---

## GET /tickets/{incident_id}
One ticket, with the full coordinator output.

**Response** `200` — `TicketDetail`: every `TicketSummary` field plus **`raw`**,
the complete stored `FaultTicket` JSON (evidence windows and KB citations
included) · `404` if the incident is unknown.

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

## GET /stream/buses
Buses the streaming service currently holds readings for — what the UI's bus
selector is populated from.

**Response** `200` — `BusListResponse` `{ "items": ["b632", ...], "count": n }`.

> The list is **whatever is in the in-memory rolling buffers**, not a roster: a
> bus appears only once it has received at least one reading off `raw.signals`,
> so this is **empty until a signal producer runs** and it resets when the app
> restarts. An empty list means "no signals yet", not "no such bus".

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
- Tables are owned by Alembic: `alembic -c backend/alembic.ini upgrade head`.
- The Kafka consumer workers start with the app lifespan when `KAFKA_ENABLED=true`.
