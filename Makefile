.PHONY: help setup test lint format coverage clean all hooks build publish secrets trivy

help:
	@echo "Available commands:"
	@echo "  make setup     - Set up development environment using uv"
	@echo "  make hooks     - Install git commit hook (runs secrets, lint, and test before commit)"
	@echo "  make secrets   - Run TruffleHog secret scanning"
	@echo "  make trivy     - Run Trivy vulnerability scanning"
	@echo "  make test      - Run tests"
	@echo "  make lint      - Run linting"
	@echo "  make format    - Format code"
	@echo "  make coverage  - Run coverage"
	@echo "  make build     - Build distribution packages using uv"
	@echo "  make publish   - Publish built packages to PyPI using uv"
	@echo "  make clean     - Clean temporary files"
	@echo "  make all       - Run all checks"

hooks:
	@chmod +x .githooks/pre-commit
	@git config core.hooksPath .githooks
	@echo "Git pre-commit hook installed and core.hooksPath set to .githooks."

secrets:
	@echo "Running TruffleHog secret scan..."
	@which trufflehog >/dev/null 2>&1 || (echo "ERROR: trufflehog is required but not installed in PATH!" >&2 && exit 1)
	@trufflehog git file://$$(pwd) --fail

trivy:
	@echo "Running Trivy vulnerability scan..."
	@docker run --rm -v $$(pwd):/src -w /src aquasec/trivy:latest fs --severity HIGH,CRITICAL --exit-code 1 .

setup: hooks
	@echo "Setting up development environment..."
	uv sync --all-extras
	@echo "Environment setup complete!"

venv:
	@echo "Creating virtual environment..."
	uv venv --allow-existing
	uv sync --all-extras
	@echo "Virtual environment created!"

test:
	@echo "Running pytest..."
	uv run pytest src/tests/ -v --tb=short

lint:
	@echo "Running linting..."
	uv run ruff check src/
	uv run ruff format --check src/

format:
	@echo "Formatting code..."
	uv run ruff format src/
	uv run ruff check --fix src/

coverage:
	@echo "Running coverage..."
	uv run pytest src/tests/ --cov=casambi_classic_ble --cov-report=html --cov-report=term-missing

build:
	@echo "Building package distributions with uv..."
	uv build

publish: build
	@echo "Publishing package to PyPI with uv..."
	uv publish

clean:
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov/ .mypy_cache dist/ build/ casambi_classic_ble.egg-info

all: secrets trivy lint test
	@echo "All checks passed successfully!"
