#!/bin/bash
# Benchmark supervisor — runs aggregator then dispatches agent with safety limits
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
CONSENSUS="$REPO_ROOT/ai-router/benchmarks/consensus.json"
PREV="/tmp/costa-benchmark-prev.json"
MAX_TIMEOUT=300  # 5 minute hard kill

# Save previous state
[ -f "$CONSENSUS" ] && cp "$CONSENSUS" "$PREV"

# Run aggregator (local Python — no API calls)
python3 "$SCRIPT_DIR/benchmark-aggregator.py" "$@"

# Dispatch agent with timeout so it can't run forever
timeout "$MAX_TIMEOUT" costa-agents dispatch benchmark-supervisor \
  "Analyze benchmark changes. Previous: $PREV Current: $CONSENSUS Mode: ${1:-daily}" \
  || echo "Benchmark agent timed out after ${MAX_TIMEOUT}s or failed (exit $?)"
