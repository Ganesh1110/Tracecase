#!/usr/bin/env bash
# Start Tracecase backend (FastAPI) using uvicorn

# Activate virtual environment
source "$(dirname "$0")/../.venv/bin/activate"

# Navigate to project root (ensure correct working dir)
cd "$(dirname "$0")/.."

# Run uvicorn server
uvicorn tracecase.ui.server:create_app --factory --reload --app-dir src --port 8000
