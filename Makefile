.PHONY: help setup venv test lint format coverage clean all hooks build publish secrets trivy audit typecheck

help:
	@echo "Available commands:"
	@echo "  make setup     - Set up development environment using uv"
	@echo "  make venv      - Create virtual environment using uv"
	@echo "  make hooks     - Install git commit hook (runs secrets, lint, and test before commit)"
	@echo "  make secrets   - Run TruffleHog secret scanning"
	@echo "  make trivy     - Run Trivy vulnerability scanning"
	@echo "  make audit     - Run pip-audit dependency vulnerability scanning"
	@echo "  make typecheck - Run mypy static type analysis"
	@echo "  make test      - Run tests"
	@echo "  make lint      - Run linting and typechecking"
	@echo "  make format    - Format code"
	@echo "  make coverage  - Run coverage"
	@echo "  make build     - Build distribution packages using uv"
	@echo "  make publish   - Displays release & publish workflow instructions"
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

audit:
	@echo "Running pip-audit dependency scan..."
	uvx pip-audit

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
	@echo "Running pytest with coverage..."
	uv run pytest src/tests/ -v --tb=short --cov=casambi_classic_ble --cov-branch --cov-fail-under=80 --cov-report=term-missing

typecheck:
	@echo "Running mypy typecheck..."
	uv run mypy src/

lint:
	@echo "Running linting and typechecking..."
	uv run ruff check src/
	uv run ruff format --check src/
	uv run mypy src/

format:
	@echo "Formatting code..."
	uv run ruff format src/
	uv run ruff check --fix src/

coverage:
	@echo "Running coverage..."
	uv run pytest src/tests/ --cov=casambi_classic_ble --cov-branch --cov-fail-under=80 --cov-report=html --cov-report=term-missing

build:
	@echo "Building package distributions with uv..."
	uv build

publish:
	@echo "NOTE: Publishing to PyPI is automated via GitHub Actions with PyPI Trusted Publishing (OIDC)."
	@echo "Trigger publish by bumping version and publishing the draft release on GitHub, or run:"
	@echo "  gh workflow run ci.yml -f job=publish"

clean:
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .coverage coverage.xml htmlcov/ .mypy_cache .ruff_cache dist/ build/ src/casambi_classic_ble.egg-info

all: secrets trivy audit lint test
	@echo "All checks passed successfully!"
