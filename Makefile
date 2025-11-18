# Makefile — Multi-Agent Fault Detection

SHELL := /bin/bash
PY := $(shell command -v python3 || command -v python)
VENV := .venv
ACTIVATE := . $(VENV)/bin/activate

ENV_FILE := .env
ENV_EXAMPLE := .env.example

# ----------------------
# Setup
# ----------------------

install:
	$(PY) -m venv $(VENV)
	$(ACTIVATE) && pip install --upgrade pip
	$(ACTIVATE) && pip install -r requirements.txt

# ----------------------
# Run UI
# ----------------------

run-ui:
	$(ACTIVATE) && streamlit run ui/streamlit_app.py

# ----------------------
# Run Demos
# ----------------------

demo-final:
	$(ACTIVATE) && python scripts/run_full_demo_with_latency.py

ticket-demo:
	$(ACTIVATE) && python scripts/run_detection_demo.py --scenario overload_trip --bus_id bus_1 \
	| python scripts/make_ticket_from_demo.py

quick-demo:
	$(ACTIVATE) && python scripts/run_detection_demo.py --scenario overload_trip --bus_id bus_1

# ----------------------
# Testing
# ----------------------

test:
	$(ACTIVATE) && pytest -q

# ----------------------
# Utilities
# ----------------------

format:
	$(ACTIVATE) && black .

lint:
	$(ACTIVATE) && ruff check .

clean:
	rm -rf $(VENV)
	find . -type d -name "__pycache__" -exec rm -rf {} +

help:
	@echo "make install        - Set up venv + install deps"
	@echo "make run-ui         - Launch Streamlit UI (streamlit_app.py)"
	@echo "make demo-final     - Full end-to-end demo with latency simulation"
	@echo "make ticket-demo    - Detection demo + ticket generation"
	@echo "make quick-demo     - Baseline detection only"
	@echo "make test           - Run tests"
	@echo "make clean          - Remove venv + caches"
