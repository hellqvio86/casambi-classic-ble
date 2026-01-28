#!/bin/bash
set -e

# Ensure we have the virtual environment and dependencies
# We assume 'make venv' has been run, or we run it if needed.
# But generally we just use 'uv run' which handles venv activation.

echo "Starting Casambi Cycle Test..."
echo "Target: Husnummer"

echo "" > test.log

# Run the python script with fallback address and debug enabled
# Redirect both stdout and stderr to both console and log file
uv run python scripts/run_test_cycle.py --address "EE:F0:3D:B9:26:A9" --debug 2>&1 | tee test.log

echo "Test Cycle Complete."
