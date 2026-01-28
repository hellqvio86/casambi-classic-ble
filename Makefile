.PHONY: help setup test lint format coverage clean all

help:
	@echo "Available commands:"
	@echo "  make setup     - Set up development environment using uv"
	@echo "  make test      - Run tests"
	@echo "  make lint      - Run linting"
	@echo "  make format    - Format code"
	@echo "  make coverage  - Run coverage"
	@echo "  make clean     - Clean temporary files"
	@echo "  make all       - Run all checks"

setup:
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
	uv run flake8 casambi_classic_ble/ tests/ --max-line-length=100
	uv run black --check casambi_classic_ble/ tests/
	uv run mypy casambi_classic_ble/ --ignore-missing-imports

format:
	@echo "Formatting code..."
	uv run black casambi_classic_ble/ tests/

coverage:
	@echo "Running coverage..."
	uv run pytest tests/ --cov=casambi_classic_ble --cov-report=html --cov-report=term-missing

clean:
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov/ .mypy_cache
	@echo "Cleanup complete!"

all: setup lint test
