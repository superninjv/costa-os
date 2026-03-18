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

select_model() {
    local free=$1
    local budget=$(( free - HEADROOM_GB ))

    if [ "$budget" -ge 12 ]; then
        echo "qwen2.5:14b"
    elif [ "$budget" -ge 6 ]; then
        echo "qwen2.5:7b"
    elif [ "$budget" -ge 3 ]; then
        echo "qwen2.5:3b"
    else
        echo "none"
    fi
}

# Check if Ollama is available
if ! command -v ollama &>/dev/null; then
    echo "qwen2.5:3b" > "$MODEL_FILE"
    exit 0
fi

# If no GPU detected, use smallest model
if [ "${VRAM_GB:-0}" -eq 0 ]; then
    echo "qwen2.5:3b" > "$MODEL_FILE"
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
