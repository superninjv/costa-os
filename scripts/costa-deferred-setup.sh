#!/bin/bash
# Costa OS Deferred Setup — runs skipped OOBE steps when internet becomes available
# Triggered by NetworkManager dispatcher or systemd timer
# Only runs if ~/.config/costa/.oobe-pending-network exists

PENDING="$HOME/.config/costa/.oobe-pending-network"
LOG="$HOME/.config/costa/deferred-setup.log"
COSTA_SHARE="/usr/share/costa-os"
COSTA_DIR="$HOME/.config/costa"

[ ! -f "$PENDING" ] && exit 0

exec > >(tee -a "$LOG") 2>&1
echo "$(date): Deferred setup starting — internet now available"

# Verify internet
ping -c1 -W3 archlinux.org &>/dev/null || { echo "No internet yet, will retry later"; exit 0; }

echo "→ Internet confirmed, running deferred setup steps..."

# Read what was deferred
STEPS=$(cat "$PENDING")

# GPU drivers
if echo "$STEPS" | grep -q "gpu_drivers"; then
    echo "→ Installing GPU drivers..."
    source "$COSTA_DIR/gpu.conf" 2>/dev/null
    case "$GPU_VENDOR" in
        amd)
            sudo -n pacman -S --noconfirm --needed vulkan-radeon lib32-vulkan-radeon 2>&1 | tail -3
            if command -v ollama &>/dev/null; then
                sudo -n pacman -S --noconfirm --needed ollama-vulkan 2>&1 | tail -1
                sudo -n mkdir -p /etc/systemd/system/ollama.service.d
                printf '[Service]\nEnvironment="OLLAMA_LLM_LIBRARY=vulkan"\nEnvironment="ROCR_VISIBLE_DEVICES=NOT_A_DEVICE"\nEnvironment="HIP_VISIBLE_DEVICES=-1"\n' \
                    | sudo -n tee /etc/systemd/system/ollama.service.d/vulkan.conf > /dev/null
                sudo -n systemctl daemon-reload
            fi
            ;;
        nvidia) sudo -n pacman -S --noconfirm --needed nvidia nvidia-utils lib32-nvidia-utils 2>&1 | tail -3 ;;
        intel) sudo -n pacman -S --noconfirm --needed vulkan-intel 2>&1 | tail -1 ;;
    esac
    echo "  ✓ GPU drivers installed"
fi

# Claude Code CLI
if echo "$STEPS" | grep -q "claude_code"; then
    echo "→ Installing Claude Code..."
    if ! command -v claude &>/dev/null; then
        if sudo -n npm install -g @anthropic-ai/claude-code 2>/dev/null; then
            echo "  ✓ Claude Code installed"
        else
            mkdir -p "$HOME/.local/lib/npm"
            npm config set prefix "$HOME/.local"
            npm install -g @anthropic-ai/claude-code 2>&1 | tail -3
            export PATH="$HOME/.local/bin:$PATH"
        fi
    fi
    # Run Claude Code setup
    if [ -f "$COSTA_SHARE/scripts/setup-claude-code.sh" ]; then
        bash "$COSTA_SHARE/scripts/setup-claude-code.sh" 2>&1
        echo "  ✓ Claude Code configured"
    fi
fi

# Ollama models
if echo "$STEPS" | grep -q "ollama_models"; then
    echo "→ Downloading AI models..."
    if command -v ollama &>/dev/null; then
        sudo -n systemctl start ollama 2>/dev/null
        sleep 3
        # Read model from config
        SMART_MODEL=$(jq -r '.ollama_smart_model // empty' "$COSTA_DIR/config.json" 2>/dev/null)
        FAST_MODEL=$(jq -r '.ollama_fast_model // empty' "$COSTA_DIR/config.json" 2>/dev/null)
        for model in $SMART_MODEL $FAST_MODEL; do
            [ -z "$model" ] && continue
            echo "  Pulling $model..."
            ollama pull "$model" 2>&1
        done
        echo "  ✓ Models downloaded"
    fi
fi

# Package installs
if echo "$STEPS" | grep -q "packages"; then
    echo "→ Installing packages..."
    CONFIG="$COSTA_DIR/config.json"
    if [ -f "$CONFIG" ]; then
        DEV=$(jq -r '.install_dev_tools // false' "$CONFIG")
        CREATIVE=$(jq -r '.install_creative // false' "$CONFIG")
        GAMING=$(jq -r '.install_gaming // false' "$CONFIG")

        if [ "$DEV" = "true" ] && [ -f "$COSTA_SHARE/packages/dev.txt" ]; then
            sudo -n pacman -S --noconfirm --needed $(grep -v '^#' "$COSTA_SHARE/packages/dev.txt" | grep -v '# AUR' | tr '\n' ' ') 2>&1 | tail -5
        fi
        if [ "$CREATIVE" = "true" ] && [ -f "$COSTA_SHARE/packages/creative.txt" ]; then
            sudo -n pacman -S --noconfirm --needed $(grep -v '^#' "$COSTA_SHARE/packages/creative.txt" | grep -v '# AUR' | tr '\n' ' ') 2>&1 | tail -5
        fi
        if [ "$GAMING" = "true" ] && [ -f "$COSTA_SHARE/packages/gaming.txt" ]; then
            sudo -n pacman -S --noconfirm --needed $(grep -v '^#' "$COSTA_SHARE/packages/gaming.txt" | grep -v '# AUR' | tr '\n' ' ') 2>&1 | tail -5
        fi
        echo "  ✓ Packages installed"
    fi
fi

# AUR packages
if echo "$STEPS" | grep -q "aur"; then
    echo "→ Installing AUR packages..."
    if command -v yay &>/dev/null; then
        if ! command -v ags &>/dev/null; then
            yay -S --noconfirm ags 2>&1 | tail -5
        fi
    fi
    echo "  ✓ AUR packages installed"
fi

# CLI wrappers
if echo "$STEPS" | grep -q "cli_wrappers"; then
    echo "→ Installing CLI wrappers..."
    if [ -d "$COSTA_SHARE/cli-wrappers" ]; then
        for wrapper_dir in "$COSTA_SHARE"/cli-wrappers/*/; do
            app=$(basename "$wrapper_dir")
            if command -v "$app" &>/dev/null || [ -f "/usr/share/applications/${app}.desktop" ]; then
                if command -v uv &>/dev/null; then
                    uv pip install --system -e "$wrapper_dir" 2>&1 | tail -1
                else
                    pip install --break-system-packages -e "$wrapper_dir" 2>&1 | tail -1
                fi
            fi
        done
    fi
    echo "  ✓ CLI wrappers installed"
fi

# Done — remove pending marker
rm -f "$PENDING"
echo "$(date): Deferred setup complete!"

# Send notification
notify-send "Costa OS" "Deferred setup complete — all packages and models are now installed." 2>/dev/null
