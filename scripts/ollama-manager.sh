#!/usr/bin/env bash
# Costa OS VRAM Manager — auto-selects the best Ollama model for available GPU memory.
# Runs as a background daemon, checks every 30 seconds.
# Writes the best model name to /tmp/ollama-smart-model for costa-ai to read.

COSTA_DIR="$HOME/.config/costa"
MODEL_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/costa"
mkdir -p "$MODEL_DIR" 2>/dev/null
MODEL_FILE="$MODEL_DIR/ollama-smart-model"
LEGACY_MODEL_FILE="/tmp/ollama-smart-model"
CHECK_INTERVAL=30
HEADROOM_GB=2  # Reserve this much VRAM for other apps

source "$COSTA_DIR/gpu.conf" 2>/dev/null

write_model() {
    echo "$1" > "$MODEL_FILE"
    # Legacy path for transition period
    echo "$1" > "$LEGACY_MODEL_FILE" 2>/dev/null || true
}

get_vram_free_gb() {
    if [ "$GPU_VENDOR" = "amd" ] && [ -n "$GPU_VRAM_USED_FILE" ] && [ -n "$GPU_VRAM_TOTAL_FILE" ]; then
        local used total
        used=$(cat "$GPU_VRAM_USED_FILE" 2>/dev/null || echo 0)
        total=$(cat "$GPU_VRAM_TOTAL_FILE" 2>/dev/null || echo 0)
        echo $(( (total - used) / 1024 / 1024 / 1024 ))
    elif [ "$GPU_VENDOR" = "nvidia" ] && command -v nvidia-smi &>/dev/null; then
        nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | awk '{printf "%d", $1/1024}'
    else
        echo 0
    fi
}

try_model() {
    # Check if a model is pulled locally before selecting it
    ollama list 2>/dev/null | grep -q "$1" && echo "$1" && return 0
    return 1
}

select_model() {
    local free=$1
    local budget=$(( free - HEADROOM_GB ))

    # LLM-judge quality tiers (2026-03-23, Claude Haiku scored):
    #   qwen3.5:9b  0.606  ~8GB   — best quality, default for 16GB GPUs
    #   qwen3.5:4b  0.581  ~5GB   — best value, 96% of 9b quality
    #   qwen3:14b   0.578  ~11GB  — similar to 4b, complementary strengths
    #   qwen3.5:2b  0.375  ~3GB   — speed-only, unreliable for general use
    #   qwen3.5:0.8b 0.231 ~1.5GB — not viable, hallucinates frequently
    # Requires Vulkan backend on RDNA4 (ROCm HIP pegs GPU at 100% idle).
    if [ "$budget" -ge 10 ]; then
        try_model "qwen3.5:9b" || try_model "qwen3:14b" || try_model "qwen2.5:14b" || try_model "qwen3.5:4b" || echo "qwen2.5:7b"
    elif [ "$budget" -ge 6 ]; then
        try_model "qwen3.5:9b" || try_model "qwen3.5:4b" || try_model "qwen2.5:7b" || echo "qwen3.5:2b"
    elif [ "$budget" -ge 4 ]; then
        try_model "qwen3.5:4b" || try_model "qwen3.5:2b" || try_model "qwen2.5:3b" || echo "none"
    elif [ "$budget" -ge 2 ]; then
        try_model "qwen3.5:2b" || try_model "qwen2.5:3b" || echo "none"
    else
        echo "none"
    fi
}

# Check if Ollama is available
if ! command -v ollama &>/dev/null; then
    write_model "qwen2.5:3b"
    exit 0
fi

# If no GPU detected, use smallest available model (CPU inference)
if [ "${VRAM_GB:-0}" -eq 0 ]; then
    if ollama list 2>/dev/null | grep -q "qwen3.5:0.8b"; then
        write_model "qwen3.5:0.8b"
    elif ollama list 2>/dev/null | grep -q "qwen3.5:2b"; then
        write_model "qwen3.5:2b"
    else
        write_model "qwen2.5:3b"
    fi
    exit 0
fi

CURRENT_MODEL=""

while true; do
    FREE_GB=$(get_vram_free_gb)
    BEST=$(select_model "$FREE_GB")

    if [ "$BEST" != "$CURRENT_MODEL" ]; then
        if [ "$BEST" = "none" ]; then
            # Unload all models (gaming mode)
            ollama stop 2>/dev/null || true
            write_model "none"
        else
            write_model "$BEST"
            # Pre-warm the model (keep_alive keeps it in VRAM)
            curl -s http://localhost:11434/api/generate \
                -d "{\"model\":\"$BEST\",\"prompt\":\"\",\"keep_alive\":\"30m\"}" \
                > /dev/null 2>&1 &
        fi
        CURRENT_MODEL="$BEST"
    fi

    sleep "$CHECK_INTERVAL"
done
