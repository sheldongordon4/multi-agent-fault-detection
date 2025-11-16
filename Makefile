# -------------------------
#   Multi-Agent Fault Detection MVP
# -------------------------

SHELL := /bin/bash
PY := $(shell command -v python3 || command -v python)
VENV := .venv
ACTIVATE := . $(VENV)/bin/activate;

APP_HOST := 0.0.0.0
APP_PORT := 8000
API_MODULE := app.api.main:app

# -------------------------
# Environment Setup
# -------------------------

install:
	$(PY) -m venv $(VENV)
	$(ACTIVATE) && pip install --upgrade pip
	$(ACTIVATE) && pip install -r requirements.txt

freeze:
	$(ACTIVATE) && pip freeze > requirements.txt

clean:
	rm -rf __pycache__ */__pycache__ .pytest_cache .streamlit
	rm -rf $(VENV)

# -------------------------
# Backend API
# -------------------------

run-api:
	$(ACTIVATE) && uvicorn $(API_MODULE) --host $(APP_HOST) --port $(APP_PORT) --reload

# -------------------------
# Streamlit UI
# -------------------------

run-ui:
	$(ACTIVATE) && streamlit run ui/streamlit_app.py

# -------------------------
# ML / Detection
# -------------------------

ticket-demo:
	$(ACTIVATE) && python scripts/run_detection_demo.py --scenario overload_trip --bus_id bus_1 \
	| python scripts/make_ticket_from_demo.py

demo-final:
	$(ACTIVATE) && python scripts/run_full_demo_with_latency.py

# -------------------------
# Testing
# -------------------------

test:
	$(ACTIVATE) && pytest -q

lint:
	$(ACTIVATE) && ruff check .

format:
	$(ACTIVATE) && black .

# -------------------------
# Docker
# -------------------------

docker-build:
	docker build -t mafaultdetection .

docker-run:
	docker run -p 8000:8000 mafaultdetection

# -------------------------
# Utilities
# -------------------------

health:
	curl http://localhost:8000/health

.PHONY: install freeze clean run-api run-ui ticket-demo demo-final test lint format docker-build docker-run health
