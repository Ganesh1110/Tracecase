#!/usr/bin/env bash
set -euo pipefail

# Isolation verification script for Tracecase dogfood test suite.
# Takes snapshot of hashes before and after test runs, and verifies zero mutation.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVIDENCE_DIR="$REPO_ROOT/tests/dogfood/evidence"
mkdir -p "$EVIDENCE_DIR"

BEFORE_SNAPSHOT="$EVIDENCE_DIR/snapshot_before.txt"
AFTER_SNAPSHOT="$EVIDENCE_DIR/snapshot_after.txt"
DIFF_OUT="$EVIDENCE_DIR/isolation_diff.txt"

TARGET_HOME="${HOME}"

# Parse optional arguments
action="compare"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --home)
      TARGET_HOME="$2"
      shift 2
      ;;
    before|after|compare|positive_control|positive_control_fake_home|full)
      action="$1"
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

take_snapshot() {
  local outfile="$1"
  local home_dir="$2"
  rm -f "$outfile"
  echo "Taking snapshot into $outfile (HOME=$home_dir)..."
  echo "TIMESTAMP: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$outfile"

  # 1. <home_dir>/.tracecase
  echo "--- HOME_TRACECASE_DIR ($home_dir/.tracecase) ---" >> "$outfile"
  if [ -d "$home_dir/.tracecase" ]; then
    find "$home_dir/.tracecase" -type f -exec shasum -a 256 {} + 2>/dev/null | sort >> "$outfile" || true
  else
    echo "NO_HOME_TRACECASE_DIR" >> "$outfile"
  fi

  # 2. <repo>/.qa_auto (legacy studio db storage)
  echo "--- REPO_DOT_QA_AUTO_DIR ---" >> "$outfile"
  if [ -d "$REPO_ROOT/.qa_auto" ]; then
    find "$REPO_ROOT/.qa_auto" -type f -exec shasum -a 256 {} + 2>/dev/null | sort >> "$outfile" || true
  else
    echo "NO_REPO_DOT_QA_AUTO_DIR" >> "$outfile"
  fi

  # 3. <repo>/.tracecase
  echo "--- REPO_DOT_TRACECASE_DIR ---" >> "$outfile"
  if [ -d "$REPO_ROOT/.tracecase" ]; then
    find "$REPO_ROOT/.tracecase" -type f -exec shasum -a 256 {} + 2>/dev/null | sort >> "$outfile" || true
  else
    echo "NO_REPO_DOT_TRACECASE_DIR" >> "$outfile"
  fi

  # 4. <repo>/recordings
  echo "--- REPO_RECORDINGS_DIR ---" >> "$outfile"
  if [ -d "$REPO_ROOT/recordings" ]; then
    find "$REPO_ROOT/recordings" -type f -exec shasum -a 256 {} + 2>/dev/null | sort >> "$outfile" || true
  else
    echo "NO_REPO_RECORDINGS_DIR" >> "$outfile"
  fi

  # 5. <repo>/studio.db
  echo "--- REPO_STUDIO_DB ---" >> "$outfile"
  if [ -f "$REPO_ROOT/studio.db" ]; then
    shasum -a 256 "$REPO_ROOT/studio.db" 2>/dev/null >> "$outfile" || true
  else
    echo "NO_REPO_STUDIO_DB" >> "$outfile"
  fi

  # 6. git status --porcelain --ignored (excluding test evidence logs)
  echo "--- GIT_STATUS_PORCELAIN_IGNORED ---" >> "$outfile"
  git -C "$REPO_ROOT" status --porcelain --ignored 2>/dev/null | grep -v "tests/dogfood/evidence/" | sort >> "$outfile" || true

  # Section summary line counts
  echo "Snapshot line counts per section for $(basename "$outfile"):"
  for sec in HOME_TRACECASE_DIR REPO_DOT_QA_AUTO_DIR REPO_DOT_TRACECASE_DIR REPO_RECORDINGS_DIR REPO_STUDIO_DB GIT_STATUS_PORCELAIN_IGNORED; do
    count=$(awk "/--- $sec/ {flag=1; next} /^--- / {flag=0} flag && NF {c++} END {print c+0}" "$outfile")
    echo "  $sec: $count lines"
  done
}

if [ "$action" = "before" ]; then
  take_snapshot "$BEFORE_SNAPSHOT" "$TARGET_HOME"
  echo "✓ Saved pre-test snapshot to $BEFORE_SNAPSHOT ($(wc -l < "$BEFORE_SNAPSHOT") total lines)"

elif [ "$action" = "after" ]; then
  take_snapshot "$AFTER_SNAPSHOT" "$TARGET_HOME"
  echo "✓ Saved post-test snapshot to $AFTER_SNAPSHOT ($(wc -l < "$AFTER_SNAPSHOT") total lines)"
  echo "Comparing snapshots with diff -u (excluding TIMESTAMP header)..."
  diff -u <(grep -v "^TIMESTAMP: " "$BEFORE_SNAPSHOT") <(grep -v "^TIMESTAMP: " "$AFTER_SNAPSHOT") > "$DIFF_OUT" || true
  if [ -s "$DIFF_OUT" ]; then
    echo "❌ ISOLATION LEAK DETECTED:"
    cat "$DIFF_OUT"
    exit 1
  else
    echo "✓ Isolation verified: diff is empty, zero external filesystem or repository state modified!"
  fi

elif [ "$action" = "positive_control" ]; then
  echo "=== POSITIVE CONTROL VERIFICATION (REPO / RECORDINGS) ==="
  take_snapshot "$BEFORE_SNAPSHOT" "$TARGET_HOME"
  echo "Planting positive control artifact: $REPO_ROOT/recordings/CONTROL.txt"
  mkdir -p "$REPO_ROOT/recordings"
  echo "UNAUTHORISED_TEST_ARTIFACT_CANARY" > "$REPO_ROOT/recordings/CONTROL.txt"
  take_snapshot "$AFTER_SNAPSHOT" "$TARGET_HOME"
  diff -u <(grep -v "^TIMESTAMP: " "$BEFORE_SNAPSHOT") <(grep -v "^TIMESTAMP: " "$AFTER_SNAPSHOT") > "$DIFF_OUT" || true
  if grep -q "CONTROL.txt" "$DIFF_OUT"; then
    echo "✓ Positive control correctly CAUGHT by isolation monitor in recordings:"
    cat "$DIFF_OUT"
  else
    echo "❌ ERROR: Positive control was NOT detected in diff!"
    exit 1
  fi
  echo "Cleaning up control artifact..."
  rm -f "$REPO_ROOT/recordings/CONTROL.txt"
  rmdir "$REPO_ROOT/recordings" 2>/dev/null || true
  take_snapshot "$AFTER_SNAPSHOT" "$TARGET_HOME"
  diff -u <(grep -v "^TIMESTAMP: " "$BEFORE_SNAPSHOT") <(grep -v "^TIMESTAMP: " "$AFTER_SNAPSHOT") > "$DIFF_OUT" || true
  if [ -s "$DIFF_OUT" ]; then
    echo "❌ ERROR: Residual diff remained after cleanup:"
    cat "$DIFF_OUT"
    exit 1
  fi
  echo "✓ Clean state restored: diff is empty."

elif [ "$action" = "positive_control_fake_home" ]; then
  echo "=== POSITIVE CONTROL VERIFICATION (FAKE HOME DIR) ==="
  FAKE_HOME=$(mktemp -d /tmp/tc_fake_home_XXXXXX)
  mkdir -p "$FAKE_HOME/.tracecase"
  echo "ORIGINAL_FAKE_CORPUS_HASH" > "$FAKE_HOME/.tracecase/corpus.db"
  take_snapshot "$BEFORE_SNAPSHOT" "$FAKE_HOME"

  echo "Planting positive control modification in fake home: $FAKE_HOME/.tracecase/leak_canary.db"
  echo "LEAKED_TRACECASE_ENTRY" > "$FAKE_HOME/.tracecase/leak_canary.db"
  take_snapshot "$AFTER_SNAPSHOT" "$FAKE_HOME"

  diff -u <(grep -v "^TIMESTAMP: " "$BEFORE_SNAPSHOT") <(grep -v "^TIMESTAMP: " "$AFTER_SNAPSHOT") > "$DIFF_OUT" || true
  if grep -q "leak_canary.db" "$DIFF_OUT"; then
    echo "✓ Positive control correctly CAUGHT in fake HOME directory:"
    cat "$DIFF_OUT"
  else
    echo "❌ ERROR: Positive control in fake home was NOT detected!"
    rm -rf "$FAKE_HOME"
    exit 1
  fi

  echo "Cleaning up fake home canary..."
  rm -f "$FAKE_HOME/.tracecase/leak_canary.db"
  take_snapshot "$AFTER_SNAPSHOT" "$FAKE_HOME"
  diff -u <(grep -v "^TIMESTAMP: " "$BEFORE_SNAPSHOT") <(grep -v "^TIMESTAMP: " "$AFTER_SNAPSHOT") > "$DIFF_OUT" || true
  if [ -s "$DIFF_OUT" ]; then
    echo "❌ ERROR: Residual diff remained after fake home cleanup:"
    cat "$DIFF_OUT"
    rm -rf "$FAKE_HOME"
    exit 1
  fi
  rm -rf "$FAKE_HOME"
  echo "✓ Clean state in fake home restored: diff is empty."

elif [ "$action" = "full" ]; then
  take_snapshot "$BEFORE_SNAPSHOT" "$TARGET_HOME"
  echo "Running full CLI test suite..."
  "$REPO_ROOT/.venv/bin/pytest" "$REPO_ROOT/tests/dogfood/cli_tests/" -q -p no:randomly
  take_snapshot "$AFTER_SNAPSHOT" "$TARGET_HOME"
  echo "Comparing snapshots..."
  diff -u <(grep -v "^TIMESTAMP: " "$BEFORE_SNAPSHOT") <(grep -v "^TIMESTAMP: " "$AFTER_SNAPSHOT") > "$DIFF_OUT" || true
  if [ -s "$DIFF_OUT" ]; then
    echo "❌ ISOLATION LEAK DETECTED:"
    cat "$DIFF_OUT"
    exit 1
  else
    echo "✓ Isolation verified: zero external filesystem or repository state modified!"
  fi
fi
