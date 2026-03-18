#!/usr/bin/env bash
# Costa OS AI Router test runner
# Usage: ./scripts/test-ai.sh [--live]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
AI_DIR="$REPO_DIR/ai-router"

LIVE=0
for arg in "$@"; do
    case "$arg" in
        --live) LIVE=1 ;;
        -h|--help)
            echo "Usage: $0 [--live]"
            echo "  --live   Also run tests that require a running Ollama instance"
            exit 0
            ;;
    esac
done

echo "=== Costa OS AI Router Tests ==="
echo "Knowledge dir: $REPO_DIR/knowledge"
echo "Test dir:      $AI_DIR/tests"
echo ""

cd "$AI_DIR"

if [ "$LIVE" -eq 1 ]; then
    echo "--- Running ALL tests (unit + live Ollama) ---"
    python3 -m pytest tests/ -v
else
    echo "--- Running unit tests (skipping live Ollama tests) ---"
    python3 -m pytest tests/ -v -m "not live"
fi

EXIT=$?
echo ""
if [ $EXIT -eq 0 ]; then
    echo "=== All tests passed ==="
else
    echo "=== Some tests failed (exit code: $EXIT) ==="
fi
exit $EXIT
