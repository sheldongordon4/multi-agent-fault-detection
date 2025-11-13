# Makefile — MAFD MVP

SHELL := /bin/bash
PY := $(shell command -v python3 || command -v python)
VENV := .venv
ACTIVATE := . $(VENV)/bin/activate;
APP_HOST := 0.0.0.0
APP_PORT := 8000
APP_MODULE := app.api.main:app

.PHONY: install venv api test fmt lint typecheck clean health docs docker-build docker-run

# Create virtual environment
venv:
	@test -d $(VENV) || $(PY) -m venv $(VENV)
	@echo "Virtual environment ready."

# Install dependencies
install: venv
	$(ACTIVATE) pip install --upgrade pip
	$(ACTIVATE) pip install -r requirements.txt

# Run API
api:
	$(ACTIVATE) uvicorn $(APP_MODULE) --host $(APP_HOST) --port $(APP_PORT) --reload

# Tests
test:
	$(ACTIVATE) PYTHONPATH=. pytest -q

# Format (black)
fmt:
	-$(ACTIVATE) black app tests

# Lint (ruff)
lint:
	-$(ACTIVATE) ruff check app tests

# Type checking (mypy)
typecheck:
	-$(ACTIVATE) PYTHONPATH=. mypy app

# Health check
health:
	curl -s "http://localhost:$(APP_PORT)/health" | $(PY) -m json.tool

# Open Swagger docs
docs:
	open "http://localhost:$(APP_PORT)/docs"

# Docker build
docker-build:
	docker build -t mafd-mvp:latest .

# Docker run
docker-run:
	docker run --rm -p 8000:8000 mafd-mvp:latest

# Cleanup
clean:
	rm -rf $(VENV) __pycache__ .pytest_cache .mypy_cache .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	@echo "Clean complete."
