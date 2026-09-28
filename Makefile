.DEFAULT_GOAL := help
SHELL := /bin/bash

PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
WEB := src/gti_copilot/web
PORT ?= 8765

.PHONY: help venv install install-web lint format typecheck test test-fast coverage e2e web-build web-test \
        demo run doctor images diagrams screenshots gif shellcheck clean soak eval-llm

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(BIN)/python:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

venv: $(BIN)/python ## Create the virtualenv

install: venv ## Install the package with dev + images extras (editable)
	$(BIN)/pip install -e ".[dev,images]"
	$(BIN)/pre-commit install || true

install-web: ## Install frontend dependencies
	cd $(WEB) && npm ci

lint: ## Ruff lint + format check
	$(BIN)/ruff check src tests scripts
	$(BIN)/ruff format --check src tests scripts

format: ## Auto-format
	$(BIN)/ruff check --fix src tests scripts
	$(BIN)/ruff format src tests scripts

typecheck: ## mypy (strict on core packages)
	$(BIN)/mypy

test: ## Unit + integration + contract tests with coverage
	$(BIN)/pytest tests/unit tests/integration --cov --cov-report=term-missing --cov-report=xml -m "not e2e and not hardware"

test-fast: ## Unit tests only, no coverage
	$(BIN)/pytest tests/unit -x -q -m "not slow"

coverage: test ## Alias for test (produces coverage.xml)

web-build: ## Build the frontend into $(WEB)/dist
	cd $(WEB) && npm run build

web-test: ## Frontend unit tests (Vitest)
	cd $(WEB) && npm test -- --run

e2e: ## Playwright end-to-end tests against the simulator
	$(BIN)/pytest tests/e2e -m e2e -q

run: ## Run the backend in simulator mode (no UI build)
	$(BIN)/gti-copilot run --mode sim --port $(PORT)

demo: ## Build UI (if Node available) and run the scripted demo drive
	@if command -v npm >/dev/null 2>&1 && [ ! -f $(WEB)/dist/index.html ]; then \
	  echo ">> building web assets"; cd $(WEB) && npm ci && npm run build; cd - >/dev/null; fi
	$(BIN)/gti-copilot run --mode sim --scenario demo_drive --port $(PORT) --open-url

doctor: ## Run environment / hardware diagnostics
	$(BIN)/gti-copilot doctor

images: ## Regenerate every README image (diagrams, screenshots, charts, GIF)
	$(BIN)/python scripts/generate_images.py --all

diagrams: ## Regenerate only the SVG/PNG diagrams
	$(BIN)/python scripts/generate_images.py --diagrams

screenshots: ## Regenerate only the UI screenshots
	$(BIN)/python scripts/generate_images.py --screenshots

gif: ## Regenerate only the demo GIF
	$(BIN)/python scripts/generate_images.py --gif

shellcheck: ## Lint shell scripts
	shellcheck scripts/*.sh

soak: ## 30 simulated minutes soak test
	$(BIN)/pytest tests/integration/test_soak.py -m slow -q

eval-llm: ## Run co-pilot evals against a real local model (optional)
	GTI_COPILOT__BACKEND=$${GTI_COPILOT__BACKEND:-ollama} $(BIN)/pytest tests/evals -q

clean: ## Remove build artifacts
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache coverage.xml htmlcov
	rm -rf $(WEB)/dist $(WEB)/node_modules/.vite
