#!/usr/bin/env bash
# Start Tracecase frontend (Vite dev server)

# Ensure we are in the project root
cd "$(dirname "$0")/.."

# Navigate to frontend directory
cd frontend

# Install dependencies if needed (npm ci)
if [ ! -d "node_modules" ]; then
  echo "Installing frontend dependencies..."
  npm ci
fi

# Run Vite dev server (default port 5173)
npm run dev
