#!/bin/bash
# Build Costa OS ISO using archiso
# Usage: sudo ./scripts/build-iso.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ISO_PROFILE="$PROJECT_DIR/iso"
WORK_DIR="/tmp/costa-iso-build"
OUT_DIR="$PROJECT_DIR/out"

if [ "$(id -u)" -ne 0 ]; then
    echo "Must run as root: sudo $0"
    exit 1
fi

echo "╔══════════════════════════════════════╗"
echo "║     Costa OS — ISO Build Script      ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ─── Prep: copy project files into airootfs ──────────────────
echo "→ Staging Costa OS files into ISO profile..."

AIROOTFS="$ISO_PROFILE/airootfs"
COSTA_SHARE="$AIROOTFS/usr/share/costa-os"

# AI router (all Python + all shell scripts/executables)
mkdir -p "$COSTA_SHARE/ai-router"
cp "$PROJECT_DIR"/ai-router/*.py "$COSTA_SHARE/ai-router/"
for cli in costa-ai costa-keybinds costa-keybinds-gui costa-ai-project-select \
           costa-ai-file-search costa-ai-screenshot costa-ai-report costa-nav \
           costa-agents costa-flow; do
    [ -f "$PROJECT_DIR/ai-router/$cli" ] && cp "$PROJECT_DIR/ai-router/$cli" "$COSTA_SHARE/ai-router/"
done
cp "$PROJECT_DIR"/ai-router/*.sh "$COSTA_SHARE/ai-router/" 2>/dev/null || true
chmod +x "$COSTA_SHARE/ai-router/costa-"* 2>/dev/null || true

# Ship pre-trained ML router model
mkdir -p "$COSTA_SHARE/ai-router/models"
if [ -f "$PROJECT_DIR/ai-router/models/ml_router.pt" ]; then
    cp "$PROJECT_DIR/ai-router/models/ml_router.pt" "$COSTA_SHARE/ai-router/models/"
    echo "  Included pre-trained ML router model from repo"
elif [ -f "$HOME/.config/costa/ml_router.pt" ]; then
    cp "$HOME/.config/costa/ml_router.pt" "$COSTA_SHARE/ai-router/models/"
    echo "  Included pre-trained ML router model from live system"
fi

# Privacy: explicitly exclude user databases and conversation logs
rm -f "$COSTA_SHARE"/ai-router/*.db "$COSTA_SHARE"/**/*.db 2>/dev/null || true
rm -f "$COSTA_SHARE"/ai-router/costa-conversation.json 2>/dev/null || true

# Scripts (wallpaper, ollama-manager, waybar generator, etc.)
mkdir -p "$COSTA_SHARE/scripts"
cp "$PROJECT_DIR"/scripts/wallpaper.sh "$COSTA_SHARE/scripts/"
cp "$PROJECT_DIR"/scripts/ollama-manager.sh "$COSTA_SHARE/scripts/"
cp "$PROJECT_DIR"/scripts/generate-waybar-config.sh "$COSTA_SHARE/scripts/" 2>/dev/null || true
cp "$PROJECT_DIR"/scripts/headless-preview.py "$COSTA_SHARE/scripts/" 2>/dev/null || true

# Installer
mkdir -p "$COSTA_SHARE/installer"
cp "$PROJECT_DIR"/installer/*.py "$COSTA_SHARE/installer/"
cp "$PROJECT_DIR"/installer/first-boot.sh "$COSTA_SHARE/installer/"
[ -f "$PROJECT_DIR/installer/costa-settings" ] && cp "$PROJECT_DIR/installer/costa-settings" "$COSTA_SHARE/installer/"

# GUI installer launcher
chmod +x "$AIROOTFS/usr/local/bin/costa-install-gui"

# Configs (includes agents, workflows, system-prompts)
cp -r "$PROJECT_DIR/configs" "$COSTA_SHARE/"

# Knowledge base
mkdir -p "$COSTA_SHARE/knowledge"
if [ -d "$PROJECT_DIR/knowledge" ]; then
    cp "$PROJECT_DIR"/knowledge/*.md "$COSTA_SHARE/knowledge/" 2>/dev/null || true
fi

# Voice assistant
if [ -d "$PROJECT_DIR/voice-assistant/src" ]; then
    mkdir -p "$COSTA_SHARE/voice-assistant"
    cp -r "$PROJECT_DIR"/voice-assistant/src/* "$COSTA_SHARE/voice-assistant/" 2>/dev/null || true
fi

# Music widget
if [ -f "$PROJECT_DIR/configs/music-widget/widget.py" ]; then
    mkdir -p "$COSTA_SHARE/music-widget"
    cp "$PROJECT_DIR/configs/music-widget/widget.py" "$COSTA_SHARE/music-widget/"
fi

# MCP server
if [ -d "$PROJECT_DIR/mcp-server" ]; then
    mkdir -p "$COSTA_SHARE/mcp-server"
    cp "$PROJECT_DIR"/mcp-server/*.py "$COSTA_SHARE/mcp-server/" 2>/dev/null || true
    cp "$PROJECT_DIR"/mcp-server/requirements.txt "$COSTA_SHARE/mcp-server/" 2>/dev/null || true
fi

# Default wallpapers
mkdir -p "$COSTA_SHARE/wallpapers"
cp "$PROJECT_DIR"/branding/wallpapers/* "$COSTA_SHARE/wallpapers/" 2>/dev/null || true
# Legacy fallback
if [ -f "$PROJECT_DIR/branding/costa-default.png" ]; then
    cp "$PROJECT_DIR/branding/costa-default.png" "$COSTA_SHARE/wallpapers/"
fi

echo "  Staged $(find "$COSTA_SHARE" -type f | wc -l) files"

# ─── Build ISO ───────────────────────────────────────────────
echo "→ Building ISO (this takes several minutes)..."
mkdir -p "$WORK_DIR" "$OUT_DIR"

mkarchiso -v -w "$WORK_DIR" -o "$OUT_DIR" "$ISO_PROFILE"

echo ""
echo "→ ISO built successfully!"
ls -lh "$OUT_DIR"/costa-os-*.iso
echo ""
echo "Test with: ./scripts/test-vm.sh"
