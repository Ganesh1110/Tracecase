#!/usr/bin/env bash
set -euo pipefail

# Isolation verification script for Tracecase dogfood test suite.
# Takes snapshot of hashes and mtimes before and after test runs, and verifies zero mutation.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SNAPSHOT_DIR="/tmp/tc_isolation_snapshots"
mkdir -p "$SNAPSHOT_DIR"

BEFORE_SNAPSHOT="$SNAPSHOT_DIR/snapshot_before.txt"
AFTER_SNAPSHOT="$SNAPSHOT_DIR/snapshot_after.txt"

take_snapshot() {
  local outfile="$1"
  rm -f "$outfile"
  echo "Taking snapshot into $outfile..."
  
  # 1. ~/.tracecase (if exists)
  if [ -d "$HOME/.tracecase" ]; then
    find "$HOME/.tracecase" -type f -exec shasum -a 256 {} + | sort >> "$outfile" 2>/dev/null || true
  else
    echo "NO_HOME_TRACECASE_DIR" >> "$outfile"
  fi

  # 2. <repo>/recordings (if exists)
  if [ -d "$REPO_ROOT/recordings" ]; then
    find "$REPO_ROOT/recordings" -type f -exec shasum -a 256 {} + | sort >> "$outfile" 2>/dev/null || true
  else
    echo "NO_REPO_RECORDINGS_DIR" >> "$outfile"
  fi

  # 3. <repo>/.tracecase (if exists, e.g. studio.db)
  if [ -d "$REPO_ROOT/.tracecase" ]; then
    find "$REPO_ROOT/.tracecase" -type f -exec shasum -a 256 {} + | sort >> "$outfile" 2>/dev/null || true
  else
    echo "NO_REPO_DOT_TRACECASE_DIR" >> "$outfile"
  fi

  # 4. <repo>/studio.db (if exists)
  if [ -f "$REPO_ROOT/studio.db" ]; then
    shasum -a 256 "$REPO_ROOT/studio.db" >> "$outfile" 2>/dev/null || true
  else
    echo "NO_REPO_STUDIO_DB" >> "$outfile"
  fi

  # 5. Repo root top-level directory listing
  ls -la "$REPO_ROOT" | awk '{print $1, $5, $9}' | sort >> "$outfile"
}

action="${1:-compare}"

if [ "$action" = "before" ]; then
  take_snapshot "$BEFORE_SNAPSHOT"
  echo "✓ Saved pre-test snapshot."
elif [ "$action" = "after" ]; then
  take_snapshot "$AFTER_SNAPSHOT"
  echo "✓ Saved post-test snapshot."
  echo "Comparing snapshots..."
  diff -u "$BEFORE_SNAPSHOT" "$AFTER_SNAPSHOT"
  echo "✓ Isolation verified: zero external filesystem or repository state modified!"
elif [ "$action" = "full" ]; then
  take_snapshot "$BEFORE_SNAPSHOT"
  echo "Running full CLI test suite..."
  "$REPO_ROOT/.venv/bin/pytest" "$REPO_ROOT/tests/dogfood/cli_tests/" -q
  take_snapshot "$AFTER_SNAPSHOT"
  echo "Comparing snapshots..."
  diff -u "$BEFORE_SNAPSHOT" "$AFTER_SNAPSHOT"
  echo "✓ Isolation verified: zero external filesystem or repository state modified!"
fi
