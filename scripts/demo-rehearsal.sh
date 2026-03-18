#!/usr/bin/env bash
# Costa OS Demo Video Rehearsal
# Interactive walkthrough of every shot in the trailer
# Press Enter to advance, times each segment

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

TOTAL_START=$(date +%s)

shot() {
    local act="$1"
    local num="$2"
    local time_range="$3"
    local title="$4"
    local instructions="$5"
    local setup_cmd="${6:-}"

    echo ""
    echo "═══════════════════════════════════════════════════════"
    printf "  ${BOLD}%s${NC} | Shot %s | ${DIM}%s${NC}\n" "$act" "$num" "$time_range"
    echo "═══════════════════════════════════════════════════════"
    echo ""
    printf "  ${CYAN}%s${NC}\n" "$title"
    echo ""
    echo "$instructions" | sed 's/^/  /'
    echo ""

    if [ -n "$setup_cmd" ]; then
        printf "  ${YELLOW}Auto-setup:${NC} %s\n" "$setup_cmd"
        eval "$setup_cmd" 2>/dev/null || true
        echo ""
    fi

    local shot_start=$(date +%s)
    printf "  ${DIM}Press Enter when this shot is done...${NC}"
    read -r
    local shot_end=$(date +%s)
    local shot_time=$((shot_end - shot_start))
    printf "  ${GREEN}Shot time: %ds${NC}\n" "$shot_time"
}

clear
echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║   Costa OS Demo Video Rehearsal       ║"
echo "  ║   Target duration: 2:00 - 2:20       ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""
echo "  This script walks through every shot in the"
echo "  demo trailer. It times each segment so you"
echo "  can pace yourself."
echo ""
echo "  Run demo-prep.sh first if you haven't already."
echo ""
printf "  ${DIM}Press Enter to begin...${NC}"
read -r

# ━━━━━━━━━━━ ACT 1: FIRST IMPRESSION (0:00 - 0:25) ━━━━━━━━━━━

shot "ACT 1" "1" "0:00-0:05" \
    "Boot splash / desktop reveal" \
    "Record the Costa OS logo animation or boot splash.
Then cut to the full desktop with Waybar, wallpaper, and clean state.
Pan across all 3 monitors if possible."

shot "ACT 1" "2" "0:05-0:15" \
    "Voice: system status query" \
    "Hold SUPER+ALT+V and say: 'what's running on my system'
Wait for the response to appear in Waybar/notification.
Show the response scrolling in the Waybar widget." \
    "rm -f /tmp/costa-conversation.json"

shot "ACT 1" "3" "0:15-0:25" \
    "Window management via voice/widget" \
    "Use the Costa widget or voice to say:
'put firefox on the top monitor and terminal on the left'
Show the windows moving to the correct monitors."

# ━━━━━━━━━━━ ACT 2: AI LAYER (0:25 - 1:00) ━━━━━━━━━━━

shot "ACT 2" "4" "0:25-0:35" \
    "Costa widget: local query" \
    "Click the Costa widget in Waybar (or type in rofi).
Ask: 'what GPU do I have'
Show the local response (should be fast, no cloud)."

shot "ACT 2" "5" "0:35-0:42" \
    "Cloud escalation demo" \
    "Ask: 'what's trending in tech news'
Show the escalation indicator (cloud icon / different color).
The response should come from Claude Haiku with web search."

shot "ACT 2" "6" "0:42-0:48" \
    "Voice: system control" \
    "Hold SUPER+ALT+V and say: 'turn the volume up'
Show the volume changing and the notification popup."

shot "ACT 2" "7" "0:48-0:55" \
    "Claude Code via Waybar" \
    "Click the Claude Code module in Waybar.
Show the terminal opening with Claude Code.
Demonstrate an MCP tool (e.g., read a file via MCP)."

shot "ACT 2" "8" "0:55-1:00" \
    "VRAM display on left monitor" \
    "Show the left portrait monitor with VRAM usage widget.
Pan to show the model currently loaded and GPU utilization."

# ━━━━━━━━━━━ ACT 3: DEVELOPER EXPERIENCE (1:00 - 1:35) ━━━━━━━━━━━

shot "ACT 3" "9" "1:00-1:08" \
    "Terminal showcase" \
    "Open Ghostty terminal.
Show starship prompt + fastfetch output.
Highlight the Costa theme and JetBrains Mono font."

shot "ACT 3" "10" "1:08-1:18" \
    "Dev tools quick cuts" \
    "Quick montage of:
- lazygit (git TUI)
- docker/lazydocker (containers)
- bottom (system monitor)
- dust (disk usage)
Each tool gets 2-3 seconds."

shot "ACT 3" "11" "1:18-1:25" \
    "Voice: project switch" \
    "Say: 'switch to my-webapp project'
Show the workspace change, editor opening, terminal cd'ing.
Demonstrate the full context switch."

shot "ACT 3" "12" "1:25-1:30" \
    "Voice: package install" \
    "Say: 'install redis'
Show the AI confirming and running pacman.
(Pre-install redis so it's instant, or show the flow)"

shot "ACT 3" "13" "1:30-1:35" \
    "Headless preview / virtual monitor" \
    "Show the headless preview feature if available.
Or show a web app previewing on a virtual display."

# ━━━━━━━━━━━ ACT 4: POLISH (1:35 - 2:00) ━━━━━━━━━━━

shot "ACT 4" "14" "1:35-1:40" \
    "Music widget" \
    "Open Spotify or a music player.
Show the floating music widget with album art.
Click through queue browsing and library search."

shot "ACT 4" "15" "1:40-1:45" \
    "Keybinds GUI" \
    "Open the keybinds configurator (SUPER+K or via Waybar).
Show recording a new keybind with the keyboard recorder.
Show conflict detection."

shot "ACT 4" "16" "1:45-1:50" \
    "Customization montage" \
    "Quick cuts showing:
- Theme switching (dark/light)
- Wallpaper change
- Waybar layout changes
2-3 seconds each."

shot "ACT 4" "17" "1:50-1:55" \
    "Settings hub" \
    "Open Settings (SUPER+I).
Browse through a few panels: display, AI models, dev tools.
Show the contextual help feature."

shot "ACT 4" "18" "1:55-2:00" \
    "Multi-monitor sweep" \
    "Final sweep across all 3 monitors.
Show different workspaces active on each.
Demonstrate the cohesive setup."

# ━━━━━━━━━━━ ACT 5: CLOSER (2:00 - 2:20) ━━━━━━━━━━━

shot "ACT 5" "19" "2:00-2:15" \
    "Text overlays (post-production)" \
    "These are added in editing:
- Key feature callouts
- 'Free and open source'
- 'Local-first AI'
- System requirements
Just note what text overlays to add."

shot "ACT 5" "20" "2:15-2:20" \
    "Logo + URL" \
    "Final frame: Costa OS logo + synoros.io/costa-os
Record a clean desktop with just the wallpaper for this."

# ━━━━━━━━━━━ SUMMARY ━━━━━━━━━━━

TOTAL_END=$(date +%s)
TOTAL_TIME=$((TOTAL_END - TOTAL_START))
TOTAL_MIN=$((TOTAL_TIME / 60))
TOTAL_SEC=$((TOTAL_TIME % 60))

echo ""
echo "═══════════════════════════════════════════════════════"
echo ""
printf "  ${BOLD}Rehearsal complete!${NC}\n"
printf "  Total time: ${CYAN}%d:%02d${NC}\n" "$TOTAL_MIN" "$TOTAL_SEC"
echo ""
if [ "$TOTAL_TIME" -lt 120 ]; then
    printf "  ${GREEN}Under 2 minutes — might need more content or slower pacing${NC}\n"
elif [ "$TOTAL_TIME" -le 140 ]; then
    printf "  ${GREEN}Right on target (2:00-2:20)${NC}\n"
else
    printf "  ${YELLOW}Over 2:20 — tighten some shots${NC}\n"
fi
echo ""
echo "  Next: Review any shots that felt off and re-run."
echo "  When ready, use wf-recorder to capture each act."
echo ""
