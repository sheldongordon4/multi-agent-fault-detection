SHELL := /bin/bash
.DEFAULT_GOAL := help

PY := $(shell command -v python3 || command -v python)
VENV := .venv

# venv layout differs by OS: Scripts/ on Windows, bin/ elsewhere.
ifeq ($(OS),Windows_NT)
BIN := $(VENV)/Scripts
else
BIN := $(VENV)/bin
endif

PYTHON := $(BIN)/python
PIP := $(BIN)/pip

ENV_FILE := .env
ENV_EXAMPLE := .env.example

ifeq ($(strip $(PY)),)
$(error No Python interpreter found on PATH)
endif

.PHONY: install venv deps env run-ui demo-final ticket-demo quick-demo test check format lint clean clean-venv help

# ----------------------
# Setup
# ----------------------

install: deps env ## Create venv, install dependencies, scaffold env file

venv: $(PYTHON) ## Create a virtual environment if missing

$(PYTHON):
	$(PY) -m venv $(VENV)

deps: venv ## Install Python dependencies into the venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

env: $(ENV_FILE) ## Copy .env from example if missing

$(ENV_FILE):
	@if [ ! -f "$(ENV_EXAMPLE)" ]; then \
		echo "Missing $(ENV_EXAMPLE); cannot scaffold $(ENV_FILE)."; \
		exit 1; \
	fi
	@if [ -f "$(ENV_FILE)" ]; then \
		echo "$(ENV_FILE) already present; leaving untouched."; \
	else \
		cp "$(ENV_EXAMPLE)" "$(ENV_FILE)"; \
		echo "Created $(ENV_FILE) from $(ENV_EXAMPLE). Update secrets before running."; \
	fi

# ----------------------
# Run UI
# ----------------------

run-ui: venv ## Launch Streamlit UI
	$(BIN)/streamlit run ui/streamlit_app.py

# ----------------------
# Run Demos
# ----------------------

demo-final: venv ## Full end-to-end demo with latency simulation
	$(PYTHON) scripts/run_full_demo_with_latency.py

ticket-demo: venv ## Detection demo + ticket generation
	$(PYTHON) scripts/run_detection_demo.py --scenario overload_trip --bus_id bus_1 | $(PYTHON) scripts/make_ticket_from_demo.py

quick-demo: venv ## Baseline detection only
	$(PYTHON) scripts/run_detection_demo.py --scenario overload_trip --bus_id bus_1

# ----------------------
# Testing
# ----------------------

test: venv ## Run pytest suite
	$(BIN)/pytest -q

check: lint test ## Run lint and tests

# ----------------------
# Utilities
# ----------------------

format: venv ## Format code with ruff
	$(BIN)/ruff format .

lint: venv ## Lint with ruff
	$(BIN)/ruff check .

clean-venv: ## Remove the virtual environment
	rm -rf $(VENV)

clean: clean-venv ## Remove venv and Python caches
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +; \
	find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete; \
	rm -rf .pytest_cache .ruff_cache .mypy_cache

help: ## Show available targets
	@echo "Available make targets:"
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_.-]+:.*##/ {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
