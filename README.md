# **Multi-Agent Fault Detection (MAFD) – MVP**

This repository contains the MVP version of a Multi-Agent Fault Detection system.  
It provides a clean, demo-ready backend that simulates SCADA and relay data, exposes a FastAPI API, and structures fault insights using a Pydantic **FaultTicket** model.

The goal of this MVP is to present a working prototype without the full production stack, following the same engineering style used in the Coherence Engine project.

---

## **Architecture Overview**

```text
           +-------------------------+
           |   SCADA Simulator       |
           |  (scada_sim.py)         |
           +------------+------------+
                        |
                        | synthetic SCADA samples
                        v
           +-------------------------+
           |   Relay Simulator       |
           |  (relay_sim.py)         |
           +------------+------------+
                        |
                        | relay events / flags
                        v
               (in-memory data flow)
                        |
                        v
+---------------------------------------------------+
|                 FastAPI Backend                    |
|                                                   |
|  +-----------------+      +--------------------+  |
|  |  /health        |      |  Future endpoints  |  |
|  |  (main.py)      |      |  (/simulate, ...)  |  |
|  +--------+--------+      +---------+----------+  |
|           |                          |            |
|           v                          v            |
|   Pydantic Models            Business Logic       |
|   (FaultTicket, ...)         (to be expanded)     |
+----------------+----------------+-----------------+
                 |
                 | JSON responses / Fault Tickets
                 v
        +---------------------------+
        |  Clients / Notebooks      |
        |  Tests (pytest + httpx)   |
        +---------------------------+
```

This MVP focuses on the backend foundation: API skeleton, data simulation, and a clear schema for fault tickets, without yet implementing multi-agent orchestration or advanced analytics.

---

## **Project Structure**

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
├── tests/
│   ├── test_health.py
│   └── test_fault_ticket_schema.py
│
├── requirements.txt
├── Dockerfile
├── Makefile
└── README.md
```

---

## **Setup (Local Development)**

### **1. Install dependencies and create virtual environment**

```bash
make install
```

This creates `.venv/` (if missing), upgrades pip, and installs all dependencies from `requirements.txt`.

### **2. (Optional) Create `.env`**

```bash
make env
```

If `.env.example` exists, it will copy it. Otherwise, it creates an empty `.env`.

### **3. Run API**

```bash
make api
```

API will start at:

```text
http://localhost:8000
```

Health endpoint:

```text
http://localhost:8000/health
```

---

## **Development Commands**

All of these run through the Makefile:

### **Run FastAPI**
```bash
make api
```

### **Run tests**
```bash
make test
```

### **Format code**
```bash
make fmt
```

### **Lint (ruff)**
```bash
make lint
```

### **Type-check (mypy)**
```bash
make typecheck
```

### **Clean caches and venv**
```bash
make clean
```

---

## **Curl Helpers**

These commands let you quickly validate API behavior.

### **Health Endpoint**
```bash
make health
```

### **Open Swagger UI**
```bash
make docs
```

---

## **Simulation Scripts**

You can generate synthetic SCADA and relay events manually:

```bash
python app/simulation/scada_sim.py
python app/simulation/relay_sim.py
```

This produces simple structured events useful for testing the fault detection pipeline.

---

## **Docker Usage**

A `Dockerfile` is included so you can build and run the API without managing a local Python environment.

### **Build Image**

```bash
make docker-build
```

This builds an image tagged `mafd-mvp:latest` using the local `Dockerfile`.

### **Run Container**

```bash
make docker-run
```

This runs the container and exposes the API on:

```text
http://localhost:8000
```

Equivalent raw Docker commands (without Make):

```bash
docker build -t mafd-mvp:latest .
docker run --rm -p 8000:8000 mafd-mvp:latest
```

---

## **Definition of Done for MVP (Goal 1)**

- Virtual environment + dependency management via `Makefile`  
- FastAPI app with routing structure and `/health` endpoint  
- SCADA and relay simulation modules in `app/simulation/`  
- `FaultTicket` Pydantic schema with example fields  
- Initial tests passing for health endpoint and schema  
- Unified `requirements.txt` (runtime + dev tools)  
- Makefile-driven developer workflow (install, api, test, fmt, lint, typecheck, clean, docker)  
- README documenting environment setup, architecture, Docker usage, and commands  

This establishes a stable foundation for future goals such as model integration, multi-agent workflows, and richer fault interpretation layers.
