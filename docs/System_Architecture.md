# Multi-Agent Fault Detection (MAFD) — Target System Architecture

**Status:** Proposal / design
**Audience:** Engineering team + utility (JPS) stakeholders
**Scope of this document:** the _target_ event-driven architecture the project is moving toward, the ML approach behind "cover all faults," the key design decisions and their rationale, and the path from a testbed proof-of-concept to a JPS-scale deployment.

---

## Table of contents

- [Multi-Agent Fault Detection (MAFD) — Target System Architecture](#multi-agent-fault-detection-mafd--target-system-architecture)
  - [Table of contents](#table-of-contents)
  - [1. Purpose \& business context](#1-purpose--business-context)
  - [2. Goals \& scope](#2-goals--scope)
  - [3. High-level architecture](#3-high-level-architecture)
  - [4. Components (services)](#4-components-services)
    - [4.1 Signal producer (Simulation → later JPS SCADA)](#41-signal-producer-simulation--later-jps-scada)
    - [4.2 Detection \& Classification service](#42-detection--classification-service)
    - [4.3 Coordinator (diagnosis) service](#43-coordinator-diagnosis-service)
    - [4.4 Streaming service](#44-streaming-service)
    - [4.5 Notification service](#45-notification-service)
    - [4.6 Persistence service](#46-persistence-service)
    - [4.7 UI](#47-ui)
    - [4.8 Assignment service (ticket ownership)](#48-assignment-service-ticket-ownership)
  - [5. Topics \& message contracts](#5-topics--message-contracts)
  - [6. The detection \& classification approach ("cover all faults")](#6-the-detection--classification-approach-cover-all-faults)
    - [6.1 Family 1 — short-circuit / open faults (supervised)](#61-family-1--short-circuit--open-faults-supervised)
    - [6.2 Family 2 — operational anomalies (unsupervised)](#62-family-2--operational-anomalies-unsupervised)
    - [6.3 Validation guard](#63-validation-guard)
  - [7. Incident lifecycle: hysteresis \& idempotency](#7-incident-lifecycle-hysteresis--idempotency)
  - [8. The live signal path (streaming → SSE → UI)](#8-the-live-signal-path-streaming--sse--ui)
  - [9. Cross-cutting concerns](#9-cross-cutting-concerns)
  - [10. Mapping from the current repo](#10-mapping-from-the-current-repo)
  - [11. Data quality notes (testbed)](#11-data-quality-notes-testbed)
  - [12. Scaling to JPS](#12-scaling-to-jps)
  - [13. Delivery phases](#13-delivery-phases)
  - [14. Open decisions](#14-open-decisions)
  - [15. Key design decisions (summary)](#15-key-design-decisions-summary)

---

## 1. Purpose & business context

MAFD is a fault detection, classification, and diagnosis system for electrical power networks. It ingests grid signals (SCADA / relay / simulated), detects disturbances in real time, classifies the fault type and locates it, retrieves the relevant Standard Operating Procedure (SOP), and produces an explainable **fault ticket** for operators.

> **Theft framing (important).** Detecting theft from SCADA _bus_ signals is coarse: it flags **suspect feeders for investigation** (load profile anomalous vs. technical-loss expectation). Pinpointing the offending connection requires **AMI / smart-meter** data (feeder-head delivery vs. sum of customer meters). The system is positioned as "**flag suspect feeders → direct field crews**," with AMI fusion as a later phase.

---

## 2. Goals & scope

**Primary goal:** prove the system works end-to-end on a controlled testbed with real and simulated data, then scale to JPS.

- **Cover all faults** — short-circuit faults (SLG, LL, LLG, LLL, LLLG), open-conductor faults (1/2/3-phase), bolted and impedance variants, plus slow operational anomalies (overload, theft, miscoordination).
- **Fast** — sub-minute trigger-to-diagnosis.
- **Explainable** — every ticket cites the SOP that justifies its recommended actions.
- **Deployable in a utility** — read-only, isolated from operational technology (OT), data stays on-premises.

**In scope now (proof-of-concept):** event-driven pipeline; supervised fault classifier + locator trained on testbed data (IEEE 13-node and IEEE 34-node feeders); operational anomaly detector; SOP retrieval; ticketing; live UI.

**Out of scope now (later phases):** JPS-scale SCADA integration, AMI fusion for theft localization, historical time-series storage for replay.

---

## 3. High-level architecture

The system is an **event-driven pipeline** of decoupled services connected by **Kafka** topics. Each service does one job; services communicate only through messages.

```
 ┌─────────────────────────┐
 │ Simulation / (later)     │   per-second readings per bus
 │ JPS SCADA  [PRODUCER]    │
 └───────────┬─────────────┘
             ▼
        TOPIC: raw.signals   ── partitioned by bus_id (per-bus ordering) ──┐
             │                                                              │
   ┌─────────┴───────────────────────────┐                    ┌────────────┴───────────────┐
   ▼                                      ▼                    ▼  (separate consumer group)
 ┌─────────────────────────────────┐                  ┌──────────────────────────────┐
 │ DETECTION & CLASSIFICATION svc  │                  │ STREAMING svc                 │
 │  • real-time trigger:           │                  │  • per-bus rolling buffer     │
 │    anomaly score + per-bus      │                  │    (in-memory deque, ~5 min)  │
 │    HYSTERESIS state machine     │                  │  • SSE → UI; snapshot on      │
 │  • on incident, classify:       │                  │    connect; filtered by the   │
 │    - short-circuit model        │                  │    bus selector               │
 │      (type / category / loc.)   │                  └──────────────┬───────────────┘
 │    - operational anomaly        │                                 │ live waveform
 │      (overload / theft / misc.) │                                 ▼
 │  → ONE event per incident       │                         ┌──────────────┐
 └───────────┬─────────────────────┘                         │  UI (browser)│
             ▼                                                │  • live chart│
       TOPIC: anomalies.detected   (type, category, location, │    + incident│
             │                      window, stats, incident_id)│    overlay   │
             ▼                                                 │  • ticket    │
 ┌─────────────────────────────────┐                          │    feed      │
 │ COORDINATOR (diagnosis) svc     │                          └──────▲───────┘
 │  • kb_retrieve → vector DB      │◄── self-hosted embeddings        │ SSE alert
 │    (matching SOP)               │                                  │
 │  • LLM (hybrid: self-hosted     │◄── data sovereignty       ┌──────┴─────────┐
 │    open model / local fallback) │                           │ NOTIFICATION   │
 │  • build FaultTicket (validated)│                           │ svc (group A)  │
 └───────────┬─────────────────────┘                           │  → SSE to UI   │
             ▼                                                  └────────────────┘
       TOPIC: faulttickets ───────────────────┬────────────────────────┘
                                               ▼ (consumer group B)
                                   ┌────────────────────────────┐
                                   │ PERSISTENCE svc             │
                                   │  → Postgres                 │
                                   │    (SQLAlchemy + Alembic)   │──► ticket history API → UI
                                   └────────────────────────────┘
```

**Why event-driven / Kafka.** Decoupling lets each concern (detection, diagnosis, notification, persistence) scale and fail independently. Kafka's **per-partition ordering** is exactly the guarantee the per-bus detection logic needs, and **consumer-group fan-out** lets notification and persistence both consume tickets without coordination.

> **As-built note.** The diagram above is the _target_; the chain it describes now runs. `raw.signals` carries **3-phase waveform frames** (one cycle per bus per message, `app/ml/waveform.py`) and is read by **two** consumer groups: `extraction` (`app/kafka/handlers/extract.py`) reduces frames to per-bus event rows and publishes them to `feeder.events`, and `streaming` collapses the same frame to per-cycle RMS for the chart. Detection then scores the row with the **event-level IsolationForest** (`app/ml/fault_detector.py`) plus the supervised classifier (`app/ml/fault_classifier.py`). Detection is a pure trigger — the Coordinator's only tool is `kb_retrieve`. See §4.2. What the diagram still describes as target rather than built is the **per-bus hysteresis state machine** (§7): the extraction worker latches on a disturbance and emits one event with a cooldown, which is the same intent in a simpler form. `scripts/produce_events.py` still replays pre-reduced rows straight onto `feeder.events` for offline work, bypassing extraction by design.

---

## 4. Components (services)

### 4.1 Signal producer (Simulation → later JPS SCADA)

Publishes per-bus, per-timestamp readings to `raw.signals`. In the proof-of-concept this is the simulator / testbed feed. In production it is a **read-only** tap into JPS's SCADA/EMS (via the historian API or an ICCP/DNP3 gateway). The producer never controls anything.

### 4.2 Detection & Classification service

**As-built:** consumes `feeder.events` — pre-reduced **per-bus event rows** (one row = one feeder snapshot in the testbed feature schema: `min_Va`, `max_Ia`, `max_I0_I1`, `max_I2_I1`, `mean_Vunb`, `recovery_Va` per bus). Scores each event with the **event-level IsolationForest** (`app/ml/fault_detector.py`, trained unsupervised on NORMAL rows) and, on a fault, runs the **supervised classifier** (`app/ml/fault_classifier.py`, RandomForest) to attach `fault_type` / `fault_category` / `location`. It emits exactly **one** `anomalies.detected` event carrying the verdict (`isFault`, anomaly score, severity), the **most-disturbed buses** (ranked by deepest voltage sag), and the `classification` — so the event is actionable.

> Where `feeder.events` comes from: the **feature-extraction bridge**, now live as the `extraction` consumer group (`app/kafka/handlers/extract.py`). It consumes `raw.signals` waveform frames, feeds a per-feeder `FeatureExtractor` (1-cycle DFT phasors + Fortescue sequence), and publishes the reduced row to `feeder.events` when a disturbance window closes. Three details are load-bearing: the trigger is **latched by the handler**, not by `cut_window()` (which fires at "now", so its window always ends `window_seconds` in the future — fine for a batch caller holding the whole waveform, unwaitable for a live one); the gate tests **sag OR current unbalance**, because unbalanced faults barely move voltage at the measuring point while balanced faults are by definition *more* balanced than a healthy feeder, so either test alone drops most of the fault classes; and the handler **does not score** — that stays in `detect.handle`, one verdict in one place. `scripts/produce_events.py` still replays pre-computed rows over `data/generated/validation_013.csv` for offline work.

**Target (future):** if the operational-anomaly (time-series) family is ever revived, a **per-bus hysteresis state machine** (NORMAL ↔ IN_INCIDENT, §7) — the extraction worker's latch-plus-cooldown is today's smaller version of it. The supervised classifier is **built** but **feeder-specific**; making it feeder-agnostic (§6.1) so it transfers across feeders is the remaining ML work. If detection ever has no classification, the coordinator falls back to inferring the fault type from the signature.

Publishes `anomalies.detected`.

### 4.3 Coordinator (diagnosis) service

Consumes `anomalies.detected`. Retrieves the matching SOP from the vector DB (`kb_retrieve`), runs the LLM (hybrid: self-hosted open model in production, local rule-based fallback offline) to produce a root-cause narrative and recommended actions, assembles a **Pydantic-validated `FaultTicket`**, and publishes it to `faulttickets`.

> In this architecture, detection is **not** an LLM tool — the anomaly event is the _trigger_ that wakes the coordinator. The coordinator's one genuine tool is SOP retrieval.

### 4.4 Streaming service

A _separate_ consumer of `raw.signals`. Maintains an **in-memory rolling buffer per bus** (a bounded `deque`, ~last 5 minutes). Serves the UI chart over **SSE**: on connect it sends the buffer snapshot (so the chart isn't empty), then streams live updates, filtered to the **bus the user selected**.

### 4.5 Notification service

Consumes `faulttickets` (consumer group A). Pushes "new incident" alerts to the UI over SSE.

### 4.6 Persistence service

Consumes `faulttickets` (consumer group B). Writes tickets to **Postgres** via **SQLAlchemy** (ORM) with **Alembic** (migrations). Exposes a ticket-history API for the UI.

### 4.7 UI

Operator-facing dashboard: live per-bus signal chart (SSE, bus selector, incident window shaded), live ticket feed (SSE), and ticket history (Postgres API). In production this integrates with the existing control-room alarm/OMS rather than standing alone.

### 4.8 Assignment service (ticket ownership)

Where the pipeline stops and people start. Every stage above produces a diagnosed ticket; nothing until now says who owns it, what state the work is in, or what was done about it. `app/assignments/` adds three tables — `operators` (a roster), `ticket_assignments` (one row per incident) and `assignment_events` (an append-only activity log, comments included) — behind a small HTTP surface.

Three properties are worth stating because each is a decision, not an accident:

- **No new Kafka topic.** Assignment is one operator clicking one button, not a stream. The pipeline is event-driven because detection genuinely fans out; a CRUD write does not. An `assignments.changed` topic earns its place the day an external OMS needs to consume it.
- **Its own table, never `fault_tickets`.** The persistence service upserts the ticket row wholesale (§4.6) and Kafka is at-least-once, so assignment state stored there is silently reset on the next redelivery. Reads LEFT JOIN from `fault_tickets`, so a missing assignment row *means* unassigned and nothing needs back-filling.
- **`work_state` is not `status`.** `FaultTicket.status` is the coordinator's diagnostic verdict, owned by the pipeline. `work_state` (unassigned → assigned → in_progress → blocked → resolved → closed) is owned by operators. Merging them would let a redelivered model guess reopen closed work.

**Operators are a roster, not accounts.** MAFD has no auth (§9), and this does not reintroduce it: there are no credentials, no sessions and no per-user scoping. The console picks who it is "acting as" and sends `X-Actor-Id`, which makes the log **attributed, not authenticated** — right-sized for a shared control-room terminal, and explicitly not an audit trail. Real identity would be SSO against the utility's directory, which is why no local password scheme was built to be thrown away later.

---

## 5. Topics & message contracts

| Topic                | Produced by                          | Consumed by                       | Partition key | Volume           |
| -------------------- | ------------------------------------ | --------------------------------- | ------------- | ---------------- |
| `raw.signals`        | Waveform producer / SCADA tap        | Extraction svc, Streaming svc     | `bus_id`      | high (~60 frames/s/bus) |
| `feeder.events`      | Extraction svc (or the replay script) | Detection svc                    | `feeder`      | one per snapshot |
| `anomalies.detected` | Detection svc                        | Coordinator svc                   | `feeder`      | one per fault    |
| `faulttickets`       | Coordinator svc                      | Notification svc, Persistence svc | `incident_id` | one per incident |

> `raw.signals` fans out to two independent consumer groups: `extraction` reduces frames to event rows for Detection, `streaming` collapses them to per-cycle RMS for the chart. Both read the frame through `app/ml/waveform.py`, so the two views cannot drift apart. Both accept **at-most-once** delivery (`run_fast_consumer`): a dropped frame costs a few samples out of a window, not a ticket, and a synchronous commit per message could never keep up with the frame rate.

**`raw.signals` payload** — a **frame**, not a reading: `{bus_id, t0, fs, Va[], Vb[], Vc[], Ia[], Ib[], Ic[]}`, one cycle of 3-phase samples for one bus. Sequence ratios (`I0/I1`, `I2/I1`) need all three phases, which is why the old single-magnitude SCADA reading could never feed the DSP (Open Decision #6, now resolved). Timestamps are reconstructed from `t0` and `fs` rather than shipped per sample — they are exactly regular by construction. Batching one cycle per message holds the topic at ~60 msg/s/bus instead of ~2k, with no information lost, because the extractor groups samples into whole cycles anyway.

**Wire format:** **JSON**, with a **Pydantic model validated at each service boundary** (`RawSignal`, `AnomalyEvent`, `FaultTicket`). This gives enforced contracts in code without running a Schema Registry; Avro/Schema Registry is a future option if multiple teams ever share the topics.

**`anomalies.detected` payload** — `incident_id`, `feeder`, the detection `verdict` (`isFault`, `anomalyScore`, `severity`), and `topBuses` (the most-disturbed buses with their per-bus signature: `minVa`, `maxIa`, `maxI0I1`, `maxI2I1`). It deliberately **does not carry the raw waveform**: the Streaming service already owns the live signal for the chart, and the UI overlays the incident window onto the waveform it is already receiving.

---

## 6. The detection & classification approach ("cover all faults")

"Cover all faults" spans **two families** that need **two different models**:

```
   FAMILY 1 — Short-circuit / open faults        FAMILY 2 — Operational anomalies
   (fast: SLG, LL, LLG, LLL, LLLG,               (slow: overload, theft,
    OPEN_1/2/3PH; bolted & impedance)             miscoordination)
        │                                              │
   SUPERVISED classifier + locator               UNSUPERVISED anomaly detector
   (feature vector per event)                     (time series + hysteresis trigger)
```

### 6.1 Family 1 — short-circuit / open faults (supervised)

Trained on the testbed (IEEE 13-node and IEEE 34-node feeders). Each training row is one fault scenario summarized into per-bus features:

- `min_Va` — voltage sag depth (per unit)
- `max_Ia` — peak current
- `max_I0_I1` — zero-sequence ratio → **ground** involvement (SLG, LLG)
- `max_I2_I1` — negative-sequence ratio → **unbalance** (SLG, LL, LLG; ~0 for balanced 3-phase)
- `mean_Vunb` — voltage unbalance
- `recovery_Va_post` — post-fault recovery

**Targets:** `fault_type`, `fault_category`, `location_km`.

**Two sub-models, split by transferability:**

- **Type / category classifier → feeder-agnostic.** The discriminating signatures are physics, not topology (`I0/I1` ⇒ ground, `I2/I1` ⇒ unbalance, both ~0 ⇒ 3-phase). Build it on **topology-independent aggregate features** (e.g. max `I0/I1` anywhere, deepest sag across buses, count of buses with `min_Va < 0.5`, mean unbalance on faulted buses). This trains across _both_ feeders at once and **transfers to new feeders, including JPS's**.
- **Location regressor → feeder-specific.** "km along branch X" only means something against a known topology — so location is a per-feeder (or topology-aware) model, refined later.

**Recommended model:** gradient-boosted trees (LightGBM / XGBoost) for the classifier and regressor — strong on tabular, fast, interpretable. A small neural net is an alternative.

### 6.2 Family 2 — operational anomalies (unsupervised)

Slow, load-related conditions (overload, theft, miscoordination) are detected on the **time-series stream** with an IsolationForest-style detector plus the hysteresis trigger (§7). Theft surfaces as a feeder load profile anomalous vs. technical-loss expectation → "investigate this feeder."

### 6.3 Validation guard

Models trained on simulation must be validated against **real fault records** (DFR / relay event data) before trusting them — the sim-to-real gap is real. The testbed plan (real data + simulation) is designed to close this.

---

## 7. Incident lifecycle: hysteresis & idempotency

A single fault produces hundreds of anomalous readings. To emit **one** event per incident (not one per second), the detector runs a **per-bus hysteresis state machine**:

```
        ┌────── anomaly_run ≥ enter_n ──────┐
        │                                   ▼
   ┌─────────┐                       ┌──────────────┐
   │ NORMAL  │                       │ IN_INCIDENT  │
   └─────────┘                       └──────────────┘
        ▲                                   │
        └────── normal_run ≥ exit_m ────────┘

   enter NORMAL→IN_INCIDENT  →  publish anomalies.detected
   enter IN_INCIDENT→NORMAL  →  publish anomalies.cleared (optional)
```

- `enter_n` consecutive anomalous readings to **declare** an incident (suppresses 1-sample blips).
- `exit_m` consecutive normal readings to **clear** it (bridges brief gaps so one event isn't split).
- **A message is published only on a state transition** — never per reading.

This requires each bus's readings to arrive **in order**, which is why `raw.signals` is **partitioned by `bus_id`** (Kafka guarantees order within a partition; many buses share a partition but each bus is consistent).

**Idempotency.** Each incident gets a deterministic `incident_id = bus_id + start_timestamp`. Re-processing (e.g. after a restart, Kafka being at-least-once) **overwrites** rather than duplicating — no duplicate tickets/alerts.

---

## 8. The live signal path (streaming → SSE → UI)

```
   user selects bus_2 in the UI
        │
        ▼
   UI opens SSE:  /stream/signals?bus_id=bus_2
        │
        ▼
   Streaming svc (already consuming raw.signals continuously):
        • sends snapshot of bus_2's rolling buffer (last ~5 min)
        • then streams new bus_2 readings live
        • old data rolls off via a bounded deque (size- or time-bounded)
        │
        ▼
   chart renders; incident window (from the ticket) is shaded as an overlay
```

- The buffer is **per bus**, maintained once in the service (not per browser); connections receive a snapshot copy.
- The **bus selector drives which slice of the firehose** each client receives — so a browser only gets the one bus it is viewing.
- Raw signals are a **time series**; they live **in memory** for the live chart. Historical waveform replay (if ever needed) is a future **time-series database** (TimescaleDB / InfluxDB), not Postgres.

---

## 9. Cross-cutting concerns

- **OT/IT isolation (non-negotiable for JPS).** The system sits in a separate network zone, consumes a **copy** of SCADA data, and is **physically incapable of issuing control commands** (IEC 62443 / NERC-CIP-style principles).
- **Data sovereignty → self-hosted models.** Grid operational data must not leave JPS premises. The **LLM is a self-hosted open model** (e.g. Llama / Mistral / Qwen) and **embeddings are a self-hosted open model** (HuggingFace `sentence-transformers`, e.g. `bge-small-en-v1.5`). The cloud LLM path is out of scope for production. The existing local fallback becomes the _primary_ offline-capable path.
- **Schemas:** JSON + Pydantic validation at every boundary (§5).
- **Delivery guarantees:** Kafka at-least-once + `incident_id` idempotency (§7).
- **High availability:** 3-broker Kafka cluster in production; the system is a monitoring overlay, so degraded monitoring is tolerable (it is not the control system).
- **Embeddings note:** switching embedding models changes vector dimensionality → the vector DB must be **rebuilt** on change.

---

## 10. Mapping from the current repo

| Current repo                                               | Evolves into                                                                         |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `app/simulation/` (orphaned toy feeds)                     | the **signal producer** → `raw.signals` (and later the SCADA tap)                    |
| `app/ml/fault_detector.py` (event IsolationForest)         | the **Detection service** (as-built); scores `feeder.events`, emits `anomalies.detected` |
| `app/ml/fault_classifier.py` (RandomForest)                | the **short-circuit classifier + locator** — type/category/location, attached to the event |
| `app/ml/feature_extractor.py` + `app/kafka/handlers/extract.py` | the **feature-extraction bridge** — live as the `extraction` consumer group, `raw.signals` → `feeder.events` |
| `app/ml/baseline_detector.py` (time-series)                | **DEPRECATED** — legacy time-series path, scripts-only, not in the app pipeline       |
| `app/rag/` (kb_loader, vector_store, retriever)            | the **Coordinator's** SOP retrieval (with self-hosted embeddings)                    |
| `app/faults/` (router, service, agent, tools, schemas)     | the **Coordinator** domain (LLM + kb_retrieve + Pydantic `FaultTicket`)              |
| `app/notification/`, `app/streaming/`, `app/persistence/`  | the Notification, Streaming, and Persistence services                                |
| `ui/streamlit_app.py` (reads ticket JSON, fake sine chart) | the **UI**, now fed by the Streaming + Notification services over SSE (real signals) |
| _(new)_                                                    | **Streaming**, **Notification**, **Persistence** services; **Kafka**; **Postgres**   |
| _(new)_ `app/assignments/`                                 | the **Assignment service** — operator roster, ticket ownership, work state, activity log (§4.8) |

---

## 11. Data quality notes (testbed)

Profiling of the testbed exports (`scripts/profile_faults.py`) found:

- **Comprehensive coverage** — SLG, LL, LLG, LLL, LLLG, OPEN_1/2/3PH; bolted + impedance; clean, designed class balance.
- **`inf` / `nan` corruption in the "orig" exports.** `min_Va` and `recovery_Va` go `inf`, `max_Ia` goes `nan`, **together across all buses in a row** — the signature of **de-energized / islanded scenarios** where the feature extractor wrote `inf`/`nan` instead of `0`.
  - `013 orig`: **51.8%** of rows affected (48% clean).
  - `034 orig`: **91.5%** affected (only 8.5% clean).
  - `013 mod`: clean — but a **separate, smaller regeneration** (1,836 rows; different `fault_phases` labels), not a cleaned subset of `013 orig`.
- **Action:** **fix the feature extractor** so de-energized buses report `0` (not `inf`/`nan`). Dropping the bad rows is a trap — the corrupted rows are the **severe** faults, so dropping biases the model toward mild faults (and gutts the 034 set). Fixing extraction recovers ~90% of 034 _and_ removes the bias.
- A small population of extreme `max_Ia` (~92 kA, a few rows) should be spot-checked as real close-in faults vs. artifacts.

---

## 12. Scaling to JPS

JPS grid (real figures): **53 substations**, **61 transmission lines**, **138 kV / 69 kV** transmission, distribution at 24 / 13.8 / 12 kV, ~14,000 km of line. That is roughly **~150 transmission buses** (thousands if every distribution feeder is instrumented).

**Throughput is not a constraint.** At realistic SCADA scan rates (every 2–4 s):

```
   ~150 buses ÷ 3-sec scan ≈ ~50 messages/sec   (even thousands of feeders ≈ a few k msg/sec)
```

Kafka handles hundreds of thousands to millions of msg/sec — JPS scale is <1% of one broker. The real engineering effort is **integration, OT security, and per-voltage-class model tuning**, never volume:

- **Partitions:** ~6–12 for all of JPS (partition _by_ `bus_id`, **not one partition per bus**).
- **Buffers:** a few hundred MB of RAM at the extreme.
- **Modeling:** a 138 kV transmission bus behaves nothing like a 13.8 kV feeder → plan **per-voltage-class models**; the feeder-agnostic classifier (§6.1) is what makes this transfer feasible.

---

## 13. Delivery phases

```
   Phase 0  Backtest on historical data      → prove ROI on JPS's own numbers, zero OT risk
   Phase 1  Live read-only pilot (few substations)
   Phase 2  All transmission buses
   Phase 3  Distribution feeders + AMI fusion for true theft localization
```

**Phase 0 is the proposal's strongest move:** run the detector/classifier offline against JPS historical data and show "we would have flagged these N feeders for theft (~US$X) and diagnosed these M faults faster" — turning the pitch from "trust us" into ROI on their own data, with no integration risk. The current testbed proof-of-concept is the technical pre-cursor to Phase 0.

---

## 14. Open decisions

1. **Feature representation** — feeder-agnostic aggregate features (recommended) vs. per-feeder columns. Shapes the whole ML layer.
2. **Hysteresis values** — `enter_n` / `exit_m` (tune on real data; relay-style "sustained for N seconds").
3. **Self-hosted LLM choice** — specific open model + serving stack (vLLM / Ollama / TGI).
4. **Embedding model** — confirm the HuggingFace model (e.g. `bge-small-en-v1.5` vs `all-MiniLM-L6-v2`); requires vector-DB rebuild on change.
5. **SCADA integration mechanism** — historian API vs ICCP vs DNP3 gateway (depends on JPS's stack; assume historian export for Phase 0).
6. ~~**`raw.signals` schema**~~ — **RESOLVED.** It carries 3-phase waveform **frames** (one cycle per bus per message, `app/ml/waveform.py`), not single-magnitude SCADA. Batching per cycle rather than per sample was the part that made it affordable: ~60 msg/s/bus instead of ~2k. `scripts/produce_waveforms.py` is the producer. See §5.
7. ~~**Live-chart fate**~~ — **RESOLVED.** The chart plots **per-cycle RMS**, reduced from the same frame the extractor consumes. Pushing ~2k raw samples/s/bus to a browser would swamp the SSE feed; RMS is ~60/s, downsamples cleanly, and is the quantity an operator already reads on SCADA, so the chart still means what it used to mean.
8. **Time-series path deprecation.** `app/ml/baseline_detector.py` + the old synthetic data/DB are being retired; `fault_detector` (event path) is the single detection path. Confirm timing.

---

## 15. Key design decisions (summary)

| Area                         | Decision                                                                              | Rationale                                                                    |
| ---------------------------- | ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Architecture style           | Event-driven, Kafka (docker-compose)                                                  | Decoupled, independently scalable; per-partition ordering fits per-bus logic |
| Topics                       | `raw.signals`, `anomalies.detected`, `faulttickets`                                   | One topic per stage; clean fan-out                                           |
| Ordering                     | Partition `raw.signals` by `bus_id`                                                   | Hysteresis state machine needs per-bus order                                 |
| Trigger                      | Per-reading scoring + per-bus hysteresis                                              | One event per incident, not one per reading                                  |
| Idempotency                  | `incident_id = bus_id + start_ts`                                                     | At-least-once delivery → overwrite, not duplicate                            |
| Fault coverage               | Two model families                                                                    | Short-circuit (supervised) + operational (unsupervised)                      |
| Classifier transferability   | Type/category feeder-agnostic; location feeder-specific                               | Physics transfers; topology does not                                         |
| Where classification runs    | Detection service                                                                     | It already holds the signal window; keeps LLM purely interpretive            |
| `anomalies.detected` content | Metadata only (no raw waveform)                                                       | Streaming service already owns the live signal                               |
| Diagnosis                    | Coordinator = LLM (hybrid) + SOP retrieval                                            | Detection is the trigger, not an LLM tool                                    |
| Live UI                      | Separate streaming service, per-bus deque, SSE, snapshot-on-connect, incident overlay | Real signals; each client gets only its selected bus                         |
| Persistence                  | Separate service, Postgres + SQLAlchemy + Alembic                                     | Fan-out via consumer group; coordinator stays pure                           |
| Messages                     | JSON + Pydantic validation                                                            | Enforced contracts without a Schema Registry                                 |
| Models in production         | Self-hosted LLM + embeddings                                                          | Data sovereignty (grid data stays on-prem)                                   |
| Security                     | Read-only, OT/IT isolated                                                             | Utility cybersecurity (IEC 62443-style)                                      |
| Scope                        | Testbed proof → JPS phases                                                            | De-risk; lead with theft/loss ROI                                            |

---

## 16. As-built status & near-term TODO

The event-driven backend is running end-to-end on real infra (Docker Postgres + Kafka). This section is the source of truth for **what exists vs. what's next** (the aspirational sections above describe the target).

### Built ✅
- **Pipeline:** `raw.signals → extraction → feeder.events → detection → anomalies.detected → coordinator → faulttickets → notification + persistence`, with **6 Kafka consumer groups** (extraction / detection / streaming / coordinator / notification / persistence) for fan-out.
- **Detection (`app/ml/fault_detector.py`):** event IsolationForest — the single detection path (detection-as-trigger).
- **Classification (`app/ml/fault_classifier.py`):** supervised RandomForest for `fault_type` / `fault_category` / `location_km`, attached to `anomalies.detected` (feeder-specific for now — see §6.1).
- **Coordinator (`app/faults/`):** LangGraph ReAct agent over **any OpenAI-compatible endpoint** (Google AI Studio `gemini-3.8-flash` by default) with the single `kb_retrieve` tool, **rate-limited + bounded retries + timeout + a process endpoint-call budget**, and a **local heuristic fallback** when no endpoint is configured. `build_chat_model()` returns the native `ChatGoogleGenerativeAI` for Google and `ChatOpenAI` on a configurable `base_url` for everything else — Gemini 3.x requires a `thought_signature` echoed back with each tool result, which the OpenAI chat-completions format has no field for, so a compat-layer ReAct loop fails on its second turn. Every other provider, including the §9 move to a self-hosted model, remains a config change rather than a rewrite. `FaultTicket` uses `StrEnum` severity/status with tolerant coercion.
- **Feature extraction DSP (`app/ml/feature_extractor.py`):** 1-cycle DFT phasors + Fortescue sequence + `_reduce_bus` + `_detect_disturbance`, all unit-tested; §11 `inf`/`nan` guard in place.
- **Persistence + API:** Postgres via SQLAlchemy async + **Alembic** (`0001_initial`); `POST /faults/diagnose`, `GET /tickets`, `GET /tickets/{incident_id}`, `GET /notifications`, SSE `/notifications/stream` + `/stream/signals`, `/health`, `/ready`.
- **Ops:** Kafka **topic bootstrap** (`app/kafka/admin.py`) + `.dlq` dead-letter routing on every topic; **`scripts/bootstrap.py`**; **Dockerfile + self-bootstrapping entrypoint** (waits for infra → migrate → build KB → uvicorn); per-domain configs; `httpx.AsyncClient` integration tests.
- **The live bridge (`app/kafka/handlers/extract.py`).** `raw.signals` now carries 3-phase waveform frames (one cycle per message per bus, `app/ml/waveform.py`) and a 6th consumer group reduces them to `feeder.events`, so a signal becomes a ticket without a replay script in the middle. Two things fell out of building it: the extractor's trigger had to be **latched by the worker** (`cut_window()` fires at "now", so its window always ends in the future — a batch caller does not care, a live one waits forever), and `ingest` had to stop rebuilding its buffer per sample (3.5k → 371k samples/s; real time needs 65k/s for a 34-bus feeder). Two more things had to be true before the chain produced the *right* answer, not merely an answer:

  - **The gate cannot be voltage sag alone.** Measured on the testbed, an SLG at the feeder head sags to ~0.995 pu while its sequence ratios move a hundredfold, so a sag-only gate never fired and `raw.signals` produced no events at all. It now fires on sag **or** current unbalance. Neither test alone is sufficient and that is the point: unbalanced faults (most of them, on a distribution feeder) barely move voltage, and balanced faults sag hard but are *more* balanced than a healthy feeder.
  - **The waveform producer needed a network propagation model.** It used to fault one bus and leave the rest at nominal, which matches no training scenario — the classifier resolved every injected fault to `OPEN_3PH`, an isolated bus beside a healthy feeder being the nearest thing it had seen. `scripts/produce_waveforms.py` now applies a **measured whole-feeder profile** (the median each monitored bus recorded per fault class in `data/generated/validation_013.csv`) to every bus. Three things in that table are counter-intuitive and all three are real: voltage barely sags at feeder-head measuring points; the faulted bus is not the most extreme (b650 carries the most current, because fault current flows *from* the source); and `mean_Vunb`, not the sequence ratios, is what separates SLG (5.96 at b671) from LLG (29.96).

`tests/test_waveform_pipeline.py` drives waveforms through the real extractor, detector, classifier and coordinator and asserts a valid `FaultTicket` comes out; `tests/test_live_chain.py` goes further and asserts the fault that went in is the fault that comes out, per fault type.
- **Concurrency isolation (`app/kafka/executors.py`).** Everything used to share the one default `asyncio.to_thread` pool (12 workers on an 8-CPU box). Six consumer groups each park a worker inside a blocking `consumer.poll()` essentially permanently, so when ML work piled on top, the streaming consumer's own `poll`/`commit` calls queued behind it, `raw.signals` stopped draining, and **the live signal chart froze whenever events flowed** (tickets and toasts kept arriving — they ride one short HTTP refetch, which survives a starved pool; a 20 Hz SSE feed does not). Now split: `run_kafka()` on a dedicated thread pool for librdkafka calls, `run_ml()` on a **`ProcessPoolExecutor`** so sklearn scoring can't hold the GIL and stall the event loop. Models load inside each worker (`app/ml/scoring.py` — picklable args only) and are warmed at startup so the ~4s cold start doesn't land on the first fault event. Falls back to a thread if the pool can't start.
- **Fast-path streaming consumer (`run_fast_consumer`).** `raw.signals` no longer uses the pause-and-commit-per-message loop (right for one LLM call per incident, hopeless at 20 readings/second — the documented ~1 msg/s cap). It consumes in batches with timed auto-commit. Trade-off: **at-most-once for this topic only** — a crash can drop a few readings from the live chart, which is transient UI data with a bounded buffer. Everything durable stays on `run_consumer` with explicit commits. Measured before/after: readings/sec through the SSE were **unchanged** during a 24s event burst (0 dropped seconds, 5.1/s either side).
- **Assignment / ticket ownership (`app/assignments/` + `frontend/src/features/assignments/`).** A roster of operators, one assignment row per incident, and an append-only activity log, on a dedicated `/assignments` page (a filterable table sized for storm-scale volume, and a detail panel whose Diagnosis tab reuses the incidents renderer). A five-column drag-and-drop board shipped alongside the table and was later removed — the table did everything the board did and kept working at volume, so the board was a second way to do the same writes. Kept off `fault_tickets` so Kafka redelivery cannot reset an operator's work — `tests/test_assignments.py::test_assignment_survives_ticket_redelivery` pins that invariant against a real database. Optimistic concurrency (`version` → `409`) stops two operators dispatching two crews to one fault. No new topic; no auth.
- **React operator console (`frontend/`).** Replaces the Streamlit browser for day-to-day use. Vite + React 19 + Tailwind v4 + shadcn/Radix, TanStack Query, Zustand. A single map-first screen: full-bleed **offline** Jamaica basemap with substation markers, IEEE13 feeder topology and parish shading, a collapsible incident list, a detail panel, and the overview (stat tiles + live signal + fault types) as a three-detent bottom drawer. See `frontend/README.md` for the map stack and its self-hosted assets.

### Next 🚧
1. **Deprecate the time-series path** — retire `baseline_detector.py` + old synthetic data/DB (Open Decision #8), and `scripts/produce_signals.py` with them: it emits single-magnitude readings that can never feed the DSP, and `produce_waveforms.py` supersedes it as the driver. The streaming chart no longer depends on the legacy path.
2. **Feeder-agnostic classifier** (§6.1) so it transfers across feeders. This is now the main ML gap.
3. **Streamlit UI → SSE** (currently reads ticket JSON), and notification email/external channels.
4. **Finish the bus namespaces.** Largely closed by the live bridge: `produce_waveforms.py` takes its bus list from the model's own feature columns, so IEEE13 ids (`b632`, `b650`, `b671`, `b675`, `b684`) now flow through `raw.signals`, `feeder.events` and the ticket alike — a ticket and its live chart finally join, and the console no longer shows two namespaces on one screen. What remains is item 1: the legacy `produce_signals.py` is the only thing still emitting `bus_1/2/3`, and it is being retired rather than renamed.
5. **A real b675 measurement.** The testbed export reports `max_Ia = 0` for b675 under every fault class while the same rows carry `I0/I1 ~ 2.0` when faulted against `~0.0001` when not. A zero phase-A current cannot have a sequence ratio, so the pair is an export artifact rather than a measurement, and the waveform producer has to special-case it. Worth resolving against the source data before the profile is trusted for anything beyond driving the demo.

```

```
