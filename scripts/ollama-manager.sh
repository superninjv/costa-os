#!/usr/bin/env bash
# Costa OS VRAM Manager — auto-selects the best Ollama model for available GPU memory.
# Runs as a background daemon, checks every 30 seconds.
# Writes the best model name to /tmp/ollama-smart-model for costa-ai to read.

COSTA_DIR="$HOME/.config/costa"
MODEL_FILE="/tmp/ollama-smart-model"
CHECK_INTERVAL=30
HEADROOM_GB=2  # Reserve this much VRAM for other apps

source "$COSTA_DIR/gpu.conf" 2>/dev/null

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

    # Prefer qwen3.5 (better quality, thinking support, 262K context).
    # Requires Vulkan backend on RDNA4 (ROCm HIP pegs GPU at 100% idle).
    # Falls back to qwen2.5 if qwen3.5 variants aren't pulled.
    #
    # VRAM requirements (Q4_K_M, benchmarked 2026-03-23):
    #   qwen3:14b   ~11GB   qwen3.5:9b  ~8GB
    #   qwen3.5:4b  ~5GB    qwen2.5:7b  ~6GB
    #   qwen3.5:2b  ~3GB    qwen2.5:3b  ~3GB
    #   qwen3.5:0.8b ~1.5GB
    # Note: qwen3.5:27b tested but NOT viable on 16GB (3.4 t/s, frequent failures)
    if [ "$budget" -ge 10 ]; then
        try_model "qwen3:14b" || try_model "qwen3.5:9b" || try_model "qwen2.5:14b" || try_model "qwen2.5:7b" || echo "qwen2.5:3b"
    elif [ "$budget" -ge 6 ]; then
        try_model "qwen3.5:9b" || try_model "qwen2.5:7b" || try_model "qwen3.5:4b" || echo "qwen2.5:3b"
    elif [ "$budget" -ge 4 ]; then
        try_model "qwen3.5:4b" || try_model "qwen2.5:3b" || try_model "qwen3.5:2b" || echo "none"
    elif [ "$budget" -ge 2 ]; then
        try_model "qwen3.5:2b" || try_model "qwen2.5:3b" || try_model "qwen3.5:0.8b" || echo "none"
    elif [ "$budget" -ge 1 ]; then
        try_model "qwen3.5:0.8b" || echo "none"
    else
        echo "none"
    fi
}

# Check if Ollama is available
if ! command -v ollama &>/dev/null; then
    echo "qwen2.5:3b" > "$MODEL_FILE"
    exit 0
fi

# If no GPU detected, use smallest available model (CPU inference)
if [ "${VRAM_GB:-0}" -eq 0 ]; then
    if ollama list 2>/dev/null | grep -q "qwen3.5:0.8b"; then
        echo "qwen3.5:0.8b" > "$MODEL_FILE"
    elif ollama list 2>/dev/null | grep -q "qwen3.5:2b"; then
        echo "qwen3.5:2b" > "$MODEL_FILE"
    else
        echo "qwen2.5:3b" > "$MODEL_FILE"
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
            echo "none" > "$MODEL_FILE"
        else
            echo "$BEST" > "$MODEL_FILE"
            # Pre-warm the model (keep_alive keeps it in VRAM)
            curl -s http://localhost:11434/api/generate \
                -d "{\"model\":\"$BEST\",\"prompt\":\"\",\"keep_alive\":\"30m\"}" \
                > /dev/null 2>&1 &
        fi
        CURRENT_MODEL="$BEST"
    fi

    sleep "$CHECK_INTERVAL"
done
