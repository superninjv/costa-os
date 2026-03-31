#!/usr/bin/env bash
# Full re-benchmark pipeline: test all models in isolation, then LLM-judge score
# Run with: bash scripts/run-full-rebenchmark.sh
set -euo pipefail

cd ~/projects/costa-os

MODELS=("qwen3.5:0.8b" "qwen3.5:2b" "qwen3.5:4b" "qwen3.5:9b" "qwen3:14b")
BENCH="python3 ai-router/tests/benchmark_qwen35.py"

echo "=== Costa OS Full Re-Benchmark Pipeline ==="
echo "Models: ${MODELS[*]}"
echo "Started: $(date)"
echo ""

# Stop VRAM manager to prevent model interference
pkill -f ollama-manager.sh 2>/dev/null || true
mkdir -p "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/costa" 2>/dev/null
echo "none" > "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/costa/ollama-smart-model"
echo "none" > /tmp/ollama-smart-model 2>/dev/null || true
echo "[1/3] VRAM manager stopped"

# Unload all models
for m in "${MODELS[@]}"; do
    curl -s http://localhost:11434/api/generate -d "{\"model\":\"$m\",\"keep_alive\":0}" > /dev/null 2>&1 || true
done
# Also unload any qwen2.5 models
for m in qwen2.5:14b qwen2.5:7b qwen2.5:3b; do
    curl -s http://localhost:11434/api/generate -d "{\"model\":\"$m\",\"keep_alive\":0}" > /dev/null 2>&1 || true
done
sleep 5
echo "[1/3] All models unloaded"
echo ""

# Benchmark each model in isolation
echo "[2/3] Running benchmarks (this takes ~30-40 min)..."
for m in "${MODELS[@]}"; do
    echo ""
    echo ">>> Benchmarking $m"

    # Unload everything first
    for prev in "${MODELS[@]}"; do
        curl -s http://localhost:11434/api/generate -d "{\"model\":\"$prev\",\"keep_alive\":0}" > /dev/null 2>&1 || true
    done
    sleep 3

    # Run benchmark (verbose, unbuffered)
    PYTHONUNBUFFERED=1 $BENCH --model "$m" --verbose

    echo ">>> $m complete"
done

echo ""
echo "[2/3] All benchmarks complete"
echo ""

# Regenerate keyword-based summary
PYTHONUNBUFFERED=1 $BENCH --summarize
echo ""

# LLM-judge re-score
echo "[3/3] Running LLM judge scoring (400 evaluations, ~10 min)..."
PYTHONUNBUFFERED=1 python3 ai-router/tests/llm_judge.py rescore-all

echo ""
echo "=== Pipeline Complete ==="
echo "Finished: $(date)"
echo ""
echo "Results:"
echo "  Keyword summary: ~/Downloads/qwen35-bench/summary.md"
echo "  Judge summary:   ~/Downloads/qwen35-bench/summary-judge.md"
echo ""

# Restart VRAM manager
~/.config/hypr/ollama-manager.sh &>/dev/null &
echo "VRAM manager restarted"
