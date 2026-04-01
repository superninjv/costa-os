#!/usr/bin/env bash
# Costa OS — Qwen3.5 RDNA4 Compatibility Test
#
# Tests whether qwen3.5 models trigger the known HIP backend bug (ROCm#5706)
# that pegs RDNA4 GPUs at 100% usage while idle. Also benchmarks quality/latency.
#
# Usage:
#   ./scripts/test-qwen35-compat.sh [model]
#   ./scripts/test-qwen35-compat.sh qwen3.5:9b
#   ./scripts/test-qwen35-compat.sh qwen3.5:4b
#
# Output: JSON verdict to stdout + file at /tmp/qwen35-compat-report.json

set -euo pipefail

MODEL="${1:-qwen3.5:9b}"
OLLAMA_URL="http://localhost:11434/api/generate"
REPORT_FILE="/tmp/qwen35-compat-report.json"
SETTLE_TIME=10
SAMPLE_DURATION=30
IDLE_THRESHOLD_PASS=10   # avg GPU% below this = PASS
IDLE_THRESHOLD_FAIL=30   # avg GPU% above this = FAIL

# ─── GPU busy % reader (AMD sysfs) ──────────────────────────
get_gpu_busy_pct() {
    local pct=0
    for f in /sys/class/drm/card*/device/gpu_busy_percent; do
        if [ -f "$f" ]; then
            pct=$(cat "$f" 2>/dev/null || echo 0)
            break
        fi
    done
    echo "$pct"
}

# Verify GPU sysfs exists
if ! ls /sys/class/drm/card*/device/gpu_busy_percent &>/dev/null; then
    echo '{"error": "No AMD GPU sysfs found (gpu_busy_percent). This test is AMD RDNA-specific."}' | tee "$REPORT_FILE"
    exit 1
fi

# Verify Ollama is running
if ! curl -sf http://localhost:11434/ >/dev/null 2>&1; then
    echo '{"error": "Ollama is not running. Start it with: systemctl start ollama"}' | tee "$REPORT_FILE"
    exit 1
fi

echo "=== Qwen3.5 RDNA4 Compatibility Test ==="
echo "Model: $MODEL"
echo ""

# ─── Step 1: Baseline GPU idle (no model loaded) ────────────
echo "[1/6] Recording baseline GPU idle % (${SETTLE_TIME}s)..."

# Unload any loaded models first
ollama stop 2>/dev/null || true
sleep 3

baseline_samples=()
for i in $(seq 1 "$SETTLE_TIME"); do
    pct=$(get_gpu_busy_pct)
    baseline_samples+=("$pct")
    sleep 1
done

baseline_avg=0
for s in "${baseline_samples[@]}"; do
    baseline_avg=$(( baseline_avg + s ))
done
baseline_avg=$(( baseline_avg / ${#baseline_samples[@]} ))
echo "  Baseline avg GPU: ${baseline_avg}%"

# ─── Step 2: Pull the model if needed ───────────────────────
echo "[2/6] Ensuring $MODEL is available..."
if ! ollama list 2>/dev/null | grep -q "${MODEL}"; then
    echo "  Pulling $MODEL (this may take a few minutes)..."
    ollama pull "$MODEL"
else
    echo "  Already available."
fi

# ─── Step 3: Warm the model ─────────────────────────────────
echo "[3/6] Warming $MODEL (loading into VRAM)..."
curl -sf "$OLLAMA_URL" \
    -d "{\"model\":\"$MODEL\",\"prompt\":\"hello\",\"stream\":false,\"keep_alive\":\"10m\",\"options\":{\"num_predict\":5}}" \
    > /dev/null 2>&1

echo "  Settling for ${SETTLE_TIME}s..."
sleep "$SETTLE_TIME"

# ─── Step 4: Sample GPU idle with model loaded ──────────────
echo "[4/6] Sampling GPU usage for ${SAMPLE_DURATION}s (model loaded, idle)..."

idle_samples=()
for i in $(seq 1 "$SAMPLE_DURATION"); do
    pct=$(get_gpu_busy_pct)
    idle_samples+=("$pct")
    printf "\r  Sample %2d/%d: GPU %3d%%" "$i" "$SAMPLE_DURATION" "$pct"
    sleep 1
done
echo ""

idle_avg=0
idle_max=0
for s in "${idle_samples[@]}"; do
    idle_avg=$(( idle_avg + s ))
    if [ "$s" -gt "$idle_max" ]; then
        idle_max="$s"
    fi
done
idle_avg=$(( idle_avg / ${#idle_samples[@]} ))
echo "  Avg GPU with model loaded: ${idle_avg}% (max: ${idle_max}%)"

# ─── Step 5: Quality + latency benchmark ────────────────────
echo "[5/6] Running quality benchmark (5 prompts)..."

quality_prompts=(
    "What is the capital of France? Answer in one word."
    "List the first 5 prime numbers separated by commas."
    "Convert 100 Celsius to Fahrenheit. Show just the number."
    "What Linux command shows disk usage? Answer in one word."
    "Is Python compiled or interpreted? Answer in one sentence."
)

latencies=()
responses=()
for i in "${!quality_prompts[@]}"; do
    prompt="${quality_prompts[$i]}"
    start_ns=$(date +%s%N)

    resp=$(curl -sf "$OLLAMA_URL" \
        -d "{\"model\":\"$MODEL\",\"prompt\":\"$prompt\",\"stream\":false,\"options\":{\"num_predict\":64,\"temperature\":0.1}}" \
        2>/dev/null)

    end_ns=$(date +%s%N)
    latency_ms=$(( (end_ns - start_ns) / 1000000 ))
    latencies+=("$latency_ms")

    response_text=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','').strip()[:200])" 2>/dev/null || echo "ERROR")
    responses+=("$response_text")

    printf "  Prompt %d: %dms — %s\n" "$((i+1))" "$latency_ms" "${response_text:0:80}"
done

# Calculate latency stats
lat_sum=0
lat_min="${latencies[0]}"
lat_max="${latencies[0]}"
for l in "${latencies[@]}"; do
    lat_sum=$(( lat_sum + l ))
    [ "$l" -lt "$lat_min" ] && lat_min="$l"
    [ "$l" -gt "$lat_max" ] && lat_max="$l"
done
lat_avg=$(( lat_sum / ${#latencies[@]} ))

# ─── Step 6: Verdict ────────────────────────────────────────
echo "[6/6] Generating verdict..."

# Unload the model
curl -sf "$OLLAMA_URL" \
    -d "{\"model\":\"$MODEL\",\"prompt\":\"\",\"keep_alive\":\"0\"}" \
    > /dev/null 2>&1

bug_present="unknown"
verdict="inconclusive"
delta=$(( idle_avg - baseline_avg ))

if [ "$idle_avg" -le "$IDLE_THRESHOLD_PASS" ]; then
    bug_present="false"
    verdict="compatible"
elif [ "$idle_avg" -ge "$IDLE_THRESHOLD_FAIL" ]; then
    bug_present="true"
    verdict="incompatible"
else
    bug_present="uncertain"
    verdict="marginal"
fi

# Build JSON report
latencies_json=$(printf '%s\n' "${latencies[@]}" | python3 -c "import sys; print([int(l.strip()) for l in sys.stdin])")
idle_json=$(printf '%s\n' "${idle_samples[@]}" | python3 -c "import sys; print([int(l.strip()) for l in sys.stdin])")
responses_json=$(python3 -c "
import json, sys
resps = $(printf '%s\n' "${responses[@]}" | python3 -c "import sys; print([l.strip() for l in sys.stdin])")
print(json.dumps(resps))
" 2>/dev/null || echo '[]')

report=$(python3 -c "
import json
report = {
    'model': '$MODEL',
    'kernel': '$(uname -r)',
    'ollama_version': '$(ollama --version 2>/dev/null | awk '{print \$NF}')',
    'gpu': '$(lspci 2>/dev/null | grep -i vga | head -1 | sed 's/.*: //' || echo unknown)',
    'baseline_gpu_pct': $baseline_avg,
    'idle_with_model_gpu_pct': $idle_avg,
    'idle_max_gpu_pct': $idle_max,
    'gpu_delta_pct': $delta,
    'idle_samples': $idle_json,
    'bug_present': $bug_present if isinstance($bug_present := '$bug_present' == 'true', bool) or True else None,
    'verdict': '$verdict',
    'thresholds': {'pass_below': $IDLE_THRESHOLD_PASS, 'fail_above': $IDLE_THRESHOLD_FAIL},
    'latency': {
        'avg_ms': $lat_avg,
        'min_ms': $lat_min,
        'max_ms': $lat_max,
        'per_prompt_ms': $latencies_json,
    },
    'quality_responses': $responses_json,
}
# Fix bug_present to proper type
report['bug_present'] = '$bug_present' == 'true' if '$bug_present' != 'uncertain' else None
print(json.dumps(report, indent=2))
")

echo "$report" > "$REPORT_FILE"

echo ""
echo "═══════════════════════════════════════════"
echo "  VERDICT: $verdict"
echo "  Baseline GPU: ${baseline_avg}%"
echo "  With $MODEL: ${idle_avg}% (max ${idle_max}%)"
echo "  Avg latency: ${lat_avg}ms"
echo "  Report: $REPORT_FILE"
echo "═══════════════════════════════════════════"

echo "$report"
