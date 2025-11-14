# Makefile — Coherence Engine / MAFD MVP

SHELL := /bin/bash

PY := $(shell command -v python3 || command -v python)
VENV := .venv
ACTIVATE := . $(VENV)/bin/activate;
RUN := $(ACTIVATE) python

APP_HOST := 0.0.0.0
APP_PORT := 8000
APP_MODULE := app.api:app

ENV_FILE := .env
ENV_EXAMPLE := .env.example

ARTIFACTS_DIR := artifacts
INCIDENTS_DIR := $(ARTIFACTS_DIR)/incidents
KB_DIR := $(ARTIFACTS_DIR)/kb
SOP_DIR := data/sop

# --------------------------------------------------------------------
# Help
# --------------------------------------------------------------------

.PHONY: help
help:
	@echo "Common targets:"
	@echo "  make venv             - Create virtual environment"
	@echo "  make install          - Install dependencies into venv"
	@echo "  make run-api          - Run FastAPI app (Uvicorn)"
	@echo "  make run-api-reload   - Run FastAPI app with reload"
	@echo "  make test             - Run tests"
	@echo "  make format           - Run code formatter (black + isort)"
	@echo "  make lint             - Run lint checks (ruff)"
	@echo "  make validate-sops    - Validate SOP headers/content"
	@echo "  make refresh-kb       - Rebuild RAG KB from data/sop"
	@echo "  make rag-test         - Quick RAG retrieval sanity test"
	@echo "  make demo-goal3       - Validate, refresh KB, then run API"
	@echo "  make docker-build     - Build Docker image"
	@echo "  make docker-run       - Run Docker container"

# --------------------------------------------------------------------
# Environment / Setup
# --------------------------------------------------------------------

.PHONY: venv
venv:
	$(PY) -m venv $(VENV)

.PHONY: ensure-env
ensure-env:
	@if [ ! -f "$(ENV_FILE)" ] && [ -f "$(ENV_EXAMPLE)" ]; then \
		echo "[make] Copying $(ENV_EXAMPLE) -> $(ENV_FILE)"; \
		cp $(ENV_EXAMPLE) $(ENV_FILE); \
	fi

.PHONY: install
install: venv ensure-env
	$(ACTIVATE) pip install --upgrade pip
	$(ACTIVATE) pip install -r requirements.txt

# --------------------------------------------------------------------
# Run / Dev
# --------------------------------------------------------------------

.PHONY: run-api
run-api:
	$(ACTIVATE) uvicorn $(APP_MODULE) --host $(APP_HOST) --port $(APP_PORT)

.PHONY: run-api-reload
run-api-reload:
	$(ACTIVATE) uvicorn $(APP_MODULE) --host $(APP_HOST) --port $(APP_PORT) --reload

run-ui:
	$(ACTIVATE) streamlit run ui/streamlit_app.py --server.address localhost --server.port 8501


ticket-demo:
	$(ACTIVATE) python scripts/run_detection_demo.py --scenario overload_trip --bus_id bus_1 | python scripts/make_ticket_from_demo.py

# --------------------------------------------------------------------
# Tests / Quality
# --------------------------------------------------------------------

.PHONY: test
test:
	$(ACTIVATE) pytest -q

.PHONY: format
format:
	$(ACTIVATE) black app scripts tests
	$(ACTIVATE) isort app scripts tests

.PHONY: lint
lint:
	$(ACTIVATE) ruff check app scripts

# --------------------------------------------------------------------
# Artifacts / Directories
# --------------------------------------------------------------------

.PHONY: ensure-dirs
ensure-dirs:
	@mkdir -p $(ARTIFACTS_DIR)
	@mkdir -p $(INCIDENTS_DIR)
	@mkdir -p $(KB_DIR)
	@mkdir -p $(SOP_DIR)

# --------------------------------------------------------------------
# Knowledge Base / SOP Utilities
# --------------------------------------------------------------------

.PHONY: validate-sops refresh-kb rag-test demo-goal3

validate-sops: ensure-dirs
	$(RUN) scripts/validate_sops.py

refresh-kb: ensure-dirs
	$(RUN) scripts/refresh_kb.py

rag-test:
	$(RUN) -c 'from app.rag.retriever import kb_retrieve_impl; print("Query: feeder overload thermal protection"); results = kb_retrieve_impl("feeder overload thermal protection"); print("Results:"); [print("-", r["source_id"], ":", r["title"]) for r in results]'

demo-goal3:
	$(MAKE) validate-sops
	$(MAKE) refresh-kb
	$(ACTIVATE) uvicorn $(APP_MODULE) --host $(APP_HOST) --port $(APP_PORT) --reload

# --------------------------------------------------------------------
# Docker
# --------------------------------------------------------------------

IMAGE_NAME := coherence-engine
CONTAINER_NAME := coherence-engine

.PHONY: docker-build docker-run docker-stop docker-clean

docker-build:
	docker build -t $(IMAGE_NAME) .

docker-run:
	docker run --rm \
		-p $(APP_PORT):$(APP_PORT) \
		--name $(CONTAINER_NAME) \
		$(IMAGE_NAME)

docker-stop:
	- docker stop $(CONTAINER_NAME)

docker-clean: docker-stop
	- docker rm $(CONTAINER_NAME)
