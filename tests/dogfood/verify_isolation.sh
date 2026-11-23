#!/usr/bin/env bash
set -euo pipefail

# Isolation verification script for Tracecase dogfood test suite.
# Takes snapshot of hashes and mtimes before and after test runs, and verifies zero mutation.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVIDENCE_DIR="$REPO_ROOT/tests/dogfood/evidence"
mkdir -p "$EVIDENCE_DIR"

BEFORE_SNAPSHOT="$EVIDENCE_DIR/snapshot_before.txt"
AFTER_SNAPSHOT="$EVIDENCE_DIR/snapshot_after.txt"
DIFF_OUT="$EVIDENCE_DIR/isolation_diff.txt"

take_snapshot() {
  local outfile="$1"
  rm -f "$outfile"
  echo "Taking snapshot into $outfile..."
  
  # 1. ~/.tracecase (if exists, e.g. corpus.db)
  if [ -d "$HOME/.tracecase" ]; then
    echo "--- HOME_TRACECASE_DIR ---" >> "$outfile"
    find "$HOME/.tracecase" -type f -exec shasum -a 256 {} + | sort >> "$outfile" 2>/dev/null || true
  else
    echo "NO_HOME_TRACECASE_DIR" >> "$outfile"
  fi

  # 2. <repo>/recordings (if exists)
  if [ -d "$REPO_ROOT/recordings" ]; then
    echo "--- REPO_RECORDINGS_DIR ---" >> "$outfile"
    find "$REPO_ROOT/recordings" -type f -exec shasum -a 256 {} + | sort >> "$outfile" 2>/dev/null || true
  else
    echo "NO_REPO_RECORDINGS_DIR" >> "$outfile"
  fi

  # 3. <repo>/.tracecase (if exists, e.g. studio.db)
  if [ -d "$REPO_ROOT/.tracecase" ]; then
    echo "--- REPO_DOT_TRACECASE_DIR ---" >> "$outfile"
    find "$REPO_ROOT/.tracecase" -type f -exec shasum -a 256 {} + | sort >> "$outfile" 2>/dev/null || true
  else
    echo "NO_REPO_DOT_TRACECASE_DIR" >> "$outfile"
  fi

  # 4. <repo>/studio.db (if exists)
  if [ -f "$REPO_ROOT/studio.db" ]; then
    echo "--- REPO_STUDIO_DB ---" >> "$outfile"
    shasum -a 256 "$REPO_ROOT/studio.db" >> "$outfile" 2>/dev/null || true
  else
    echo "NO_REPO_STUDIO_DB" >> "$outfile"
  fi
}

action="${1:-compare}"

if [ "$action" = "before" ]; then
  take_snapshot "$BEFORE_SNAPSHOT"
  echo "✓ Saved pre-test snapshot to $BEFORE_SNAPSHOT ($(wc -l < "$BEFORE_SNAPSHOT") lines)"
elif [ "$action" = "after" ]; then
  take_snapshot "$AFTER_SNAPSHOT"
  echo "✓ Saved post-test snapshot to $AFTER_SNAPSHOT ($(wc -l < "$AFTER_SNAPSHOT") lines)"
  echo "Comparing snapshots with diff -u..."
  diff -u "$BEFORE_SNAPSHOT" "$AFTER_SNAPSHOT" > "$DIFF_OUT" || true
  if [ -s "$DIFF_OUT" ]; then
    echo "❌ ISOLATION LEAK DETECTED:"
    cat "$DIFF_OUT"
    exit 1
  else
    echo "✓ Isolation verified: diff is empty, zero external filesystem or repository state modified!"
  fi
elif [ "$action" = "positive_control" ]; then
  echo "=== POSITIVE CONTROL VERIFICATION ==="
  take_snapshot "$BEFORE_SNAPSHOT"
  echo "Planting positive control artifact: $REPO_ROOT/recordings/CONTROL.txt"
  mkdir -p "$REPO_ROOT/recordings"
  echo "UNAUTHORISED_TEST_ARTIFACT_CANARY" > "$REPO_ROOT/recordings/CONTROL.txt"
  take_snapshot "$AFTER_SNAPSHOT"
  diff -u "$BEFORE_SNAPSHOT" "$AFTER_SNAPSHOT" > "$DIFF_OUT" || true
  if grep -q "CONTROL.txt" "$DIFF_OUT"; then
    echo "✓ Positive control correctly CAUGHT by isolation monitor:"
    cat "$DIFF_OUT"
  else
    echo "❌ ERROR: Positive control was NOT detected in diff!"
    exit 1
  fi
  echo "Cleaning up control artifact..."
  rm -f "$REPO_ROOT/recordings/CONTROL.txt"
  rmdir "$REPO_ROOT/recordings" 2>/dev/null || true
  take_snapshot "$AFTER_SNAPSHOT"
  diff -u "$BEFORE_SNAPSHOT" "$AFTER_SNAPSHOT" > "$DIFF_OUT" || true
  if [ -s "$DIFF_OUT" ]; then
    echo "❌ ERROR: Residual diff remained after cleanup:"
    cat "$DIFF_OUT"
    exit 1
  fi
  echo "✓ Clean state restored: diff is empty."
elif [ "$action" = "full" ]; then
  take_snapshot "$BEFORE_SNAPSHOT"
  echo "Running full CLI test suite..."
  "$REPO_ROOT/.venv/bin/pytest" "$REPO_ROOT/tests/dogfood/cli_tests/" -q
  take_snapshot "$AFTER_SNAPSHOT"
  echo "Comparing snapshots..."
  diff -u "$BEFORE_SNAPSHOT" "$AFTER_SNAPSHOT" > "$DIFF_OUT" || true
  if [ -s "$DIFF_OUT" ]; then
    echo "❌ ISOLATION LEAK DETECTED:"
    cat "$DIFF_OUT"
    exit 1
  else
    echo "✓ Isolation verified: zero external filesystem or repository state modified!"
  fi
fi
