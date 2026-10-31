.PHONY: help setup test lint format coverage clean all hooks build publish

help:
	@echo "Available commands:"
	@echo "  make setup     - Set up development environment using uv"
	@echo "  make hooks     - Install git commit hook (runs lint and test before commit)"
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
	@mkdir -p .git/hooks 2>/dev/null || true
	@cp .githooks/pre-commit .git/hooks/pre-commit 2>/dev/null || true
	@chmod +x .git/hooks/pre-commit 2>/dev/null || true
	@git config core.hooksPath .githooks 2>/dev/null || true
	@echo "Git commit hook installed."

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
	uv run pytest tests/ -v --tb=short

lint:
	@echo "Running linting..."
	uv run ruff check casambi_classic_ble/ tests/
	uv run ruff format --check casambi_classic_ble/ tests/
	uv run mypy casambi_classic_ble/ --ignore-missing-imports

format:
	@echo "Formatting code..."
	uv run ruff format casambi_classic_ble/ tests/
	uv run ruff check --fix casambi_classic_ble/ tests/

coverage:
	@echo "Running coverage..."
	uv run pytest tests/ --cov=casambi_classic_ble --cov-report=html --cov-report=term-missing

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
	@echo "Cleanup complete!"

all: setup lint test
