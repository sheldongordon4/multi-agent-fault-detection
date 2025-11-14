
# **Multi-Agent Fault Detection (MAFD) – MVP (Goals 1–4 Completed)**

This repository now contains a **demo‑ready MVP** of the Multi‑Agent Fault Detection system.

It includes:

- FastAPI backend (Goal 1)  
- Baseline detector and synthetic/real signal integration (Goal 2)  
- Ticket generation pipeline (Goal 3)  
- Streamlit UI with **real flagged signals**, reasoning summary, and full end‑to‑end demo flow (Goal 4)

This README reflects **all completed goals so far**.

---

# **Architecture Overview**

```text
           +-------------------------+
           |     SCADA Simulator     |
           |     (scada_sim.py)      |
           +-----------+-------------+
                       |
                       v
           +-------------------------+
           |     Relay Simulator     |
           |    (relay_sim.py)       |
           +-----------+-------------+
                       |
                       v
+------------------------------------------------------+
|                Baseline Detector (Goal 2)            |
|   - Synthetic/real signal loader                     |
|   - Anomaly scoring + summary stats                  |
+-----------+------------------------------------------+
            |
            v
+------------------------------------------------------+
|              Ticket Generator (Goal 3)               |
|   - Converts detector summary → Fault Ticket JSON    |
|   - Adds evidence windows + metadata                 |
+-----------+------------------------------------------+
            |
            v
+------------------------------------------------------+
|       Streamlit UI – Fault Browser (Goal 4)          |
|   - Ticket list + severity triage                    |
|   - Ticket detail view                               |
|   - Reasoning summary + AI reasoning (demo mode)     |
|   - **Real flagged signals plotted from CSV/API**     |
+------------------------------------------------------+
```

---

# **Project Structure**

```text
multi-agent-fault-detection/
│
├── app/
│   ├── api/
│   │   └── main.py
│   ├── core/
│   │   └── config.py
│   ├── models/
│   │   └── fault_ticket.py
│   └── simulation/
│       ├── scada_sim.py
│       └── relay_sim.py
│
├── ml/
│   ├── baseline_detector.py
│   └── (detector assets...)
│
├── scripts/
│   ├── run_detection_demo.py        # Goal 2 & 4
│   ├── make_ticket_from_demo.py     # Goal 3
│   └── signal_writer.py             # Goal 4 real signal support
│
├── ui/
│   └── streamlit_app.py             # Goal 4
│
├── artifacts/
│   ├── incidents/                   # Goal 3 tickets
│   └── signals/                     # Goal 4 signal CSVs
│
├── tests/
│   └── ...
│
├── Makefile
├── requirements.txt
└── README.md
```

---

# **Goal 1 – Backend Foundation (Complete)**

- FastAPI skeleton  
- `/health` endpoint  
- SCADA + relay simulators  
- Pydantic FaultTicket model  
- Dockerfile + Makefile workflow  
- Initial tests (pytest + httpx)  
- Environment management (`make install`, `.venv`)

---

# **Goal 2 – Data + Model Integration (Complete)**

- Baseline anomaly detector implemented:
  - Synthetic data loader  
  - IsolationForest model  
  - Summary statistics  
- Output structured:
  - `nPoints`
  - `nAnomalies`
  - `meanAnomalyScore`
- `run_detection_demo.py` produces:
  - Clean JSON payload  
  - Passes through pipeline cleanly  
- Added optional:
  - `anomalyRate`
  - Better naming & structure

---

# **Goal 3 – Ticket Generation Pipeline (Complete)**

- `make_ticket_from_demo.py` converts detector summary → structured ticket  
- Includes:
  - scenario
  - busId
  - faultType
  - severity heuristic
  - summary block
  - recommended actions
  - reasoning root cause
  - evidence windows  
- Writes tickets to:

```
artifacts/incidents/<ticket_id>.json
```

- Ensures compatibility with Goal 4 UI

---

# **Goal 4 – Streamlit UI & End‑to‑End Demo (Complete)**

Goal 4 delivers a **demo-ready dashboard** and **real flagged signal visualization**, completing the full MVP loop.

## ✔ What Goal 4 Adds

### **1. Real Flagged Signal Visualization**
Each detection run writes real signal data to:

```
artifacts/signals/demo_signals.csv
```

CSV schema:

| column     | meaning                        |
|------------|--------------------------------|
| timestamp  | ISO-8601 timestamp             |
| metric     | "current" (or other)           |
| value      | numeric signal value           |
| bus_id     | bus name                       |
| scenario   | scenario label                 |

The Streamlit UI automatically plots this data and labels it **source: csv**.

### **2. Ticket Evidence Aligned to Real Signals**
`run_detection_demo.py` now returns:

- `signalWindowStart`
- `signalWindowEnd`
- `signalMetric`

`make_ticket_from_demo.py` uses these to produce evidence windows that match the CSV range exactly.

### **3. Updated Detector Pipeline**
`scripts/run_detection_demo.py`:
- Generates timestamps aligned to `nPoints`
- Creates a demo waveform (or real values later)
- Saves them via `save_signals(...)`
- Injects window metadata into detector JSON

### **4. Streamlit Fault Browser**
UI features:

- Ticket list (with color‑coded severity)
- Detailed ticket view  
- Summary, root cause, recommended actions  
- **Flagged signal plot from CSV**  
- AI reasoning (demo mode)
- Raw JSON view  
- KB citations section  

---

# **Running the Full Demo (End‑to‑End)**

### **1. Generate Ticket + Real Signal Data**

```bash
make ticket-demo
```

This triggers:

- Detector run  
- Real signal CSV written  
- Ticket created under `artifacts/incidents/`  

### **2. Run the UI**

```bash
make run-ui
```

Open:

```
http://localhost:8501
```

### **3. Validate**

You should see:

- A ticket in the list  
- Severity badge  
- Summary + reasoning  
- **Real signal plot**  
- AI reasoning (demo mode)  
- Raw JSON  

This fully satisfies the dean’s requirements.

---

# **Requirements**

See `requirements.txt` for full dependency list:

```
fastapi
uvicorn[standard]
pydantic
python-dotenv

pytest
httpx
black
ruff
mypy

pandas
numpy
scikit-learn
sqlalchemy

langchain
langchain-community
langchain-openai
chromadb

streamlit
requests
```

---

# **Docker Usage**

Build:

```bash
make docker-build
```

Run:

```bash
make docker-run
```

---

# **Definition of Done (Goals 1–4)**

- Full FastAPI backend  
- Detector + model integration  
- Ticket generation  
- Real flagged signals exported  
- UI plotting real signal windows  
- Reasoning summary + AI reasoning demo  
- End-to-end pipeline demonstrably working  
- Updated README documenting entire workflow  

---

# **Next Steps (Future Goals)**

- Integrate real SCADA backend  
- Replace demo waveform in detector with actual samples  
- Add FastAPI `/signals/window` endpoint  
- Implement multi-agent reasoning layer (Phase 2)  
- Add trend dashboards + operator tools  
