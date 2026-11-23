#!/usr/bin/env bash
set -euo pipefail

# Complete test runner for Tracecase Dogfood Suite
# Runs linting, isolation checks, flow-mapping audit, and pytest suite.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "================================================================================"
echo "TRACECASE COMPLETE DOGFOOD TEST SUITE RUNNER"
echo "================================================================================"

echo ""
echo "[1/5] Running AST Assertion Quality Linter..."
"$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/tests/dogfood/check_assertion_quality.py"

echo ""
echo "[2/5] Running Flow-to-Test Traceability Audit..."
"$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/tests/dogfood/check_flow_test_mapping.py"

echo ""
echo "[3/5] Taking Pre-Run Filesystem Isolation Snapshot..."
"$REPO_ROOT/tests/dogfood/verify_isolation.sh" before

echo ""
echo "[4/5] Executing Full CLI Dogfood Pytest Suite..."
"$REPO_ROOT/.venv/bin/pytest" "$REPO_ROOT/tests/dogfood/cli_tests/" -v --tb=short

echo ""
echo "[5/5] Verifying Filesystem Isolation (Zero Mutation)..."
"$REPO_ROOT/tests/dogfood/verify_isolation.sh" after

echo ""
echo "================================================================================"
echo "✓ ALL DOGFOOD VERIFICATIONS PASSED SUCCESSFULLY!"
echo "================================================================================"
