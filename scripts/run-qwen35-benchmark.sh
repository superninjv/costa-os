#!/usr/bin/env bash
# Costa OS — Qwen 3.5 Full Benchmark Suite
#
# Pulls all qwen3.5 models (0.8b-9b), benchmarks each against 100 prompts,
# and generates comparison tables for research-1.md.
#
# Usage:
#   ./scripts/run-qwen35-benchmark.sh              # Full run (all models + thinking)
#   ./scripts/run-qwen35-benchmark.sh --quick       # Skip thinking mode tests
#   ./scripts/run-qwen35-benchmark.sh --model 4b    # Single model only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BENCHMARK="$PROJECT_DIR/ai-router/tests/benchmark_qwen35.py"
OUTPUT_DIR="$HOME/Downloads/qwen35-bench"
RESEARCH_DOC="$HOME/Downloads/research-1.md"

MODELS=("qwen3.5:0.8b" "qwen3.5:2b" "qwen3.5:4b" "qwen3.5:9b")
QUICK=false
SINGLE_MODEL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --quick) QUICK=true; shift ;;
        --model) SINGLE_MODEL="$2"; shift 2 ;;
        *) echo "Unknown flag: $1"; exit 1 ;;
    esac
done

echo "╔══════════════════════════════════════════════╗"
echo "║  Qwen 3.5 Model Benchmark Suite             ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  Output:    $OUTPUT_DIR"
echo "  Research:  $RESEARCH_DOC"
echo "  Thinking:  $( $QUICK && echo 'SKIP' || echo 'YES' )"
echo ""

mkdir -p "$OUTPUT_DIR"

# ─── Step 1: Pull missing models ─────────────────────────────
echo "▶ Step 1: Checking models..."
for model in "${MODELS[@]}"; do
    if ollama list 2>/dev/null | grep -q "${model}"; then
        echo "  ✓ ${model} (already pulled)"
    else
        echo "  ↓ Pulling ${model}..."
        ollama pull "${model}" 2>&1 | tail -1
    fi
done
echo ""

# ─── Step 2: Run benchmarks ──────────────────────────────────
THINKING_FLAG=""
if ! $QUICK; then
    THINKING_FLAG="--test-thinking"
fi

if [ -n "$SINGLE_MODEL" ]; then
    echo "▶ Step 2: Benchmarking qwen3.5:${SINGLE_MODEL}..."
    python3 "$BENCHMARK" --model "qwen3.5:${SINGLE_MODEL}" $THINKING_FLAG --verbose
else
    echo "▶ Step 2: Benchmarking all models..."
    python3 "$BENCHMARK" --all $THINKING_FLAG --verbose
fi

# ─── Step 3: Generate summary ────────────────────────────────
echo ""
echo "▶ Step 3: Generating summary..."
python3 "$BENCHMARK" --summarize

# ─── Step 4: Append to research doc ──────────────────────────
if [ -f "$OUTPUT_DIR/summary.md" ] && [ -f "$RESEARCH_DOC" ]; then
    echo ""
    echo "▶ Step 4: Appending to research doc..."

    # Check if already appended
    if grep -q "Qwen 3.5 Model Benchmark Results" "$RESEARCH_DOC" 2>/dev/null; then
        echo "  Research doc already has benchmark section — skipping append"
        echo "  (Manual update: see $OUTPUT_DIR/summary.md)"
    else
        echo "" >> "$RESEARCH_DOC"
        echo "---" >> "$RESEARCH_DOC"
        echo "" >> "$RESEARCH_DOC"
        cat "$OUTPUT_DIR/summary.md" >> "$RESEARCH_DOC"
        echo "  ✓ Appended to $RESEARCH_DOC"
    fi
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Benchmark complete!                        ║"
echo "╚══════════════════════════════════════════════╝"
echo "  Reports:  $OUTPUT_DIR/qwen35-*.json"
echo "  Summary:  $OUTPUT_DIR/summary.md"
echo "  Research: $RESEARCH_DOC"
