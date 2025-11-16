# 🌐 Multi-Agent Fault Detection (MAFD) – MVP

This repository contains a **demo‑ready MVP** of a fault detection system designed for synthetic SCADA and relay data. It demonstrates a clean end‑to‑end pipeline from **signal simulation → anomaly detection → ticket generation → UI visualization → timed final demo**.

The MVP emphasizes:
- Fast detection  
- Clear, explainable reasoning  
- SOP citation inclusion  
- Real signal visualization  
- <60s trigger‑to‑diagnosis performance  

---

# 🏗️ System Overview

The system includes:

- **SCADA & Relay Simulators**  
  Synthetic data generation (voltage, current, frequency, and event flags).  

- **Anomaly Detector**  
  IsolationForest baseline with window extraction and CSV export for UI.

- **Ticket Generator**  
  Produces structured JSON tickets with:
  - reasoning summary  
  - root cause  
  - SOP citations  
  - evidence windows  

- **Streamlit UI**  
  Allows browsing tickets, viewing real signal plots, and reading reasoning/citations.

- **Final Demo Runner**  
  Measures full pipeline latency and prints the final ticket and timing result.

---

# 🔄 End‑to‑End Flow (Simplified Diagram)

```
SCADA Simulation
        ↓
Relay Event Injection
        ↓
Baseline ML Detector
        ↓
Evidence Window Extraction
        ↓
Fault Ticket Builder (reasoning + SOP citations)
        ↓
Streamlit UI (signals + ticket)
        ↓
Final Demo Runner (<60s latency)
```

---

# 🧩 Component Summary

### **1. Simulation Layer**
Generates synthetic grid signals and event flags.

### **2. Detection Layer**
- Loads synthetic/real signal data  
- Runs IsolationForest anomaly detection  
- Extracts anomaly windows  
- Saves CSV for UI plotting  

### **3. Ticket Layer**
Builds a complete fault ticket containing:
- scenario & bus  
- fault type  
- reasoning  
- SOP citations  
- evidence window timestamps  
- structured JSON output  

### **4. UI Layer**
Streamlit dashboard that shows:
- Ticket list  
- Severity indicators  
- Real signal visualization from CSV  
- Reasoning & SOP citations  
- Raw JSON  

### **5. Demo Layer**
Single‑command final demo:
```
make demo-final
```
Runs:
1. Detection  
2. Ticket generator  
3. Latency measurement  
4. Final output presentation  

---

# 🎫 Ticket JSON Structure (Example)

```json
{
  "ticket_id": "LOCAL-overload_trip-bus_1",
  "scenario": "overload_trip",
  "busId": "bus_1",
  "faultType": "Overload Trip on bus_1",
  "severity": "high",
  "summary": "An anomaly consistent with Overload Trip was detected...",
  "root_cause": "Potential overload condition inferred...",
  "kb_citations": [
    {"source_id": "SOP-OVLD-001", "title": "Feeder Overload – Guidance"}
  ],
  "evidence": [
    {
      "start_timestamp": "...",
      "end_timestamp": "...",
      "metric": "current"
    }
  ]
}
```

---

# 🚀 Final Demo (<60s Trigger → Diagnosis)

Run the complete pipeline:

```bash
make demo-final
```

This:
- runs the detector  
- generates the ticket  
- loads reasoning + SOP citations  
- measures latency  
- prints the final JSON output  

**Typical latency:** ~4–6 seconds.

---

# 📊 Streamlit UI

Launch the dashboard:

```bash
make run-ui
```

Visit:

```
http://localhost:8501
```

UI Features:
- Ticket list  
- Severity indicators  
- Real signal line plot  
- Reasoning summary  
- SOP citations  
- Raw JSON  

---

# 🐳 Docker Usage

Build:
```bash
make docker-build
```

Run:
```bash
make docker-run
```

---

# 🧪 Testing

Run:
```bash
make test
```

Tests cover:
- Detector behavior  
- Ticket schema  
- Basic API health  
- Latency benchmark  

---

# 🗂 Documentation Included

This repo includes a full documentation suite:

- **API_Reference.md**  
- **Agent_Architecture.md**  
- **Agent_Prompt_Guide.md**  
- **Knowledge_Base_Index.md**  
- **Testing_Report.md**  

---

# 📌 Project Status

The MVP is **complete**, fully demonstrable, and ready for stakeholder review or Phase 2 development.

