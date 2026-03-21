#!/bin/bash
# Record Costa OS showcase video in two takes on the headless monitor
# Usage: ./scripts/demo-record.sh [take1|take2|both]
#
# Take 1: VM install timelapse (records HDMI-A-2 while VM runs)
# Take 2: 8 Claude Codes working (records HDMI-A-2 grid)
#
# Recordings saved to ~/Videos/costa-demo/

set -e

OUT_DIR="$HOME/Videos/costa-demo"
mkdir -p "$OUT_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MONITOR="HDMI-A-2"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}→${NC} $1"; }
ok()  { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }

record_start() {
    local output="$1"
    local description="$2"
    log "Recording $description to $output"
    log "Press Ctrl+C to stop recording"
    echo ""

    # wf-recorder: native Wayland recorder, captures specific output
    wf-recorder \
        --output "$MONITOR" \
        --codec libx264 \
        --codec-param crf=18 \
        --codec-param preset=fast \
        --file "$output" \
        --pixel-format yuv420p
}

take1_install() {
    local OUTPUT="$OUT_DIR/take1_install_${TIMESTAMP}.mp4"

    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║   TAKE 1: VM Install Timelapse       ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
    echo ""

    warn "Before recording:"
    echo "  1. Make sure HDMI-A-2 (workspace 5) is clean"
    echo "  2. Launch the VM: ./scripts/test-vm.sh"
    echo "  3. Move the VM window to workspace 5 if it isn't there"
    echo "  4. Come back here and press Enter to start recording"
    echo ""
    read -p "Press Enter when the VM is running on $MONITOR..."

    record_start "$OUTPUT" "VM install"

    ok "Take 1 saved: $OUTPUT"
    echo ""
    echo "Post-process (speed up 15x):"
    echo "  ffmpeg -i \"$OUTPUT\" -filter:v \"setpts=0.067*PTS\" -an \"$OUT_DIR/take1_fast.mp4\""
}

take2_claudes() {
    local OUTPUT="$OUT_DIR/take2_claudes_${TIMESTAMP}.mp4"

    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║   TAKE 2: 8 Claude Codes Working     ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
    echo ""

    log "Launching 8 Claude Code instances on workspace 5..."
    bash "$(dirname "$0")/demo-8-claudes.sh" 5

    echo ""
    log "Waiting 5s for windows to tile..."
    sleep 5

    # Switch to the workspace so it's active
    hyprctl dispatch workspace 5

    echo ""
    warn "Check workspace 5 — all 8 should be tiled and streaming"
    read -p "Press Enter when it looks good to start recording..."

    record_start "$OUTPUT" "8 Claude Codes"

    ok "Take 2 saved: $OUTPUT"
    echo ""
    echo "Post-process (trim to best 30s, hero loop):"
    echo "  ffmpeg -i \"$OUTPUT\" -ss 10 -t 30 -c copy \"$OUT_DIR/take2_trimmed.mp4\""
}

# ─── Main ─────────────────────────────────────

echo ""
echo -e "${CYAN}Costa OS Showcase — Recording Session${NC}"
echo "Monitor: $MONITOR (1920x1080)"
echo "Output:  $OUT_DIR"
echo ""

case "${1:-both}" in
    take1)
        take1_install
        ;;
    take2)
        take2_claudes
        ;;
    both)
        take1_install
        echo ""
        echo "════════════════════════════════════════"
        echo ""
        take2_claudes
        ;;
    *)
        echo "Usage: $0 [take1|take2|both]"
        exit 1
        ;;
esac

echo ""
echo "════════════════════════════════════════"
echo ""
ok "All takes recorded!"
echo ""
echo "Files in $OUT_DIR:"
ls -lh "$OUT_DIR"/*.mp4 2>/dev/null
echo ""
echo "Next steps:"
echo "  1. Speed up take 1: ffmpeg -i take1_*.mp4 -filter:v 'setpts=0.067*PTS' -an take1_fast.mp4"
echo "  2. Trim take 2 to best 30s for hero banner"
echo "  3. Import both into DaVinci Resolve for final edit + voiceover"
echo "  4. Export hero banner (15-30s, no audio, H.264) and standalone (60-90s, with audio)"
