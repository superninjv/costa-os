#!/usr/bin/env bash
# Costa OS Demo Preparation
# Gets the desktop into a clean, demo-ready state before recording

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
fail()  { echo -e "${RED}[✗]${NC} $1"; }

echo "═══════════════════════════════════════"
echo "  Costa OS Demo Preparation"
echo "═══════════════════════════════════════"
echo ""

# 1. Clear conversation state
echo "--- Clearing state ---"
rm -f /tmp/costa-conversation.json
rm -f /tmp/costa-ai-*.tmp
info "Conversation history cleared"

# 2. Kill extraneous processes
echo ""
echo "--- Cleaning processes ---"
# Kill any leftover costa-ai processes
pkill -f "costa-ai" 2>/dev/null && info "Killed stale costa-ai processes" || info "No stale costa-ai processes"
# Kill any stale rofi instances
pkill rofi 2>/dev/null && info "Killed stale rofi" || info "No stale rofi"

# 3. Ensure Ollama is running
echo ""
echo "--- Checking Ollama ---"
if systemctl is-active --quiet ollama; then
    info "Ollama service is running"
else
    warn "Ollama not running, starting..."
    sudo systemctl start ollama
    sleep 2
    info "Ollama started"
fi

# 4. Pre-load the 14B model
echo ""
echo "--- Loading AI model ---"
warn "Pre-warming qwen2.5:14b (this may take a moment)..."
echo "" | ollama run qwen2.5:14b --nowordwrap 2>/dev/null
info "qwen2.5:14b loaded and warm"

# 5. Verify Waybar
echo ""
echo "--- Checking Waybar ---"
if pgrep -x waybar > /dev/null; then
    info "Waybar is running"
else
    warn "Waybar not running, starting..."
    waybar &disown
    sleep 2
    info "Waybar started"
fi

# 6. Verify wallpaper
echo ""
echo "--- Checking wallpaper ---"
if pgrep -x mpvpaper > /dev/null; then
    info "mpvpaper wallpaper is running"
else
    warn "Wallpaper not running — start it manually or check ~/.config/hypr/wallpaper.sh"
fi

# 7. Check wf-recorder
echo ""
echo "--- Checking recording tools ---"
if command -v wf-recorder &>/dev/null; then
    info "wf-recorder is installed"
else
    fail "wf-recorder not found — install with: sudo pacman -S wf-recorder"
fi

if command -v slurp &>/dev/null; then
    info "slurp is installed (region selection)"
else
    fail "slurp not found — install with: sudo pacman -S slurp"
fi

# 8. Check monitors
echo ""
echo "--- Monitor check ---"
MONITOR_COUNT=$(hyprctl monitors -j 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
EXPECTED_MONITORS="${COSTA_DEMO_MONITORS:-1}"
if [ "$MONITOR_COUNT" -ge "$EXPECTED_MONITORS" ]; then
    info "$MONITOR_COUNT monitor(s) detected"
elif [ "$MONITOR_COUNT" -ge 1 ]; then
    warn "$MONITOR_COUNT monitor(s) detected (expected $EXPECTED_MONITORS, set COSTA_DEMO_MONITORS to adjust)"
else
    fail "Could not detect monitors"
fi

# 9. Close unnecessary windows for clean desktop
echo ""
echo "--- Desktop cleanup ---"
info "Tip: Close unnecessary windows manually for a clean shot"

# 10. Summary
echo ""
echo "═══════════════════════════════════════"
echo "  Preparation complete!"
echo "═══════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Open Firefox + Ghostty in clean state"
echo "  2. Run: ./scripts/demo-test-queries.sh"
echo "  3. Run: ./scripts/demo-rehearsal.sh"
