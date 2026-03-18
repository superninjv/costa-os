#!/usr/bin/env bash
# Costa OS — Interactive Mouse Button Mapper
# Press buttons to identify them, then configure what they do.

BOLD='\033[1m'
DIM='\033[2m'
CYAN='\033[36m'
WARM='\033[38;2;194;120;73m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
RESET='\033[0m'

G502_NAMES=(
    "Left Click"
    "Right Click"
    "Middle Click (scroll press)"
    "Back (thumb lower)"
    "Forward (thumb upper)"
    "DPI Shift (sniper, below scroll)"
    "G7 (left of left-click, back)"
    "G8 (left of left-click, front)"
)

show_header() {
    clear
    echo -e "${CYAN}╔══════════════════════════════════════════╗${RESET}"
    echo -e "${CYAN}║  ${BOLD}Costa OS Mouse Button Mapper${RESET}${CYAN}             ║${RESET}"
    echo -e "${CYAN}╚══════════════════════════════════════════╝${RESET}"
    echo ""
}

show_current() {
    echo -e "${BOLD}Current Mappings:${RESET}"
    echo -e "${DIM}$(printf '─%.0s' {1..55})${RESET}"
    local buttons
    buttons=$(costa-keybinds --json mouse 2>/dev/null)
    echo "$buttons" | python3 -c "
import json, sys
buttons = json.load(sys.stdin)
for b in buttons:
    idx = b['index']
    if idx > 7: continue
    phys = b['physical']
    action = b['action']
    pt = b['passthrough']
    if pt:
        code = b.get('hypr_code', '')
        status = f'OS passthrough [{code}]' if code else 'OS passthrough'
    else:
        status = f'{action} (hardware)'
    marker = '✓' if pt and idx > 2 else ' '
    print(f'  {idx}: {phys:<40s} {status} {marker}')
" 2>/dev/null
    echo ""
}

detect_button() {
    echo -e "${YELLOW}Press any mouse button to identify it...${RESET}"
    echo -e "${DIM}(left/right/middle are ignored, press q to cancel)${RESET}"
    echo ""

    # Listen for button events
    local result
    result=$(sudo timeout 15 evtest /dev/input/event3 2>/dev/null | grep -m1 "BTN_.*value 1" | grep -v "BTN_LEFT\|BTN_RIGHT\|BTN_MIDDLE")

    if [ -z "$result" ]; then
        # Try the direct device too
        result=$(sudo timeout 15 evtest /dev/input/event8 2>/dev/null | grep -m1 "BTN_.*value 1" | grep -v "BTN_LEFT\|BTN_RIGHT\|BTN_MIDDLE")
    fi

    if [ -z "$result" ]; then
        echo -e "${RED}No button detected${RESET}"
        return 1
    fi

    local code name
    code=$(echo "$result" | grep -oP 'code \K\d+')
    name=$(echo "$result" | grep -oP '\((\w+)\)' | tr -d '()')
    local idx=$((code - 272))
    local physical="${G502_NAMES[$idx]:-Button $idx}"

    echo -e "${GREEN}Detected:${RESET} ${BOLD}$physical${RESET}"
    echo -e "  evdev: $name (code $code)"
    echo -e "  Hyprland: mouse:$code"
    echo -e "  ratbag index: $idx"
    echo ""

    echo -e "${WARM}What should this button do?${RESET}"
    echo -e "  ${BOLD}1${RESET}. Keep as OS passthrough (bindable in Hyprland/apps)"
    echo -e "  ${BOLD}2${RESET}. DPI shift (sniper mode)"
    echo -e "  ${BOLD}3${RESET}. DPI cycle up"
    echo -e "  ${BOLD}4${RESET}. DPI cycle down"
    echo -e "  ${BOLD}5${RESET}. Profile cycle"
    echo -e "  ${BOLD}6${RESET}. Nothing (leave as-is)"
    echo ""
    read -rp "  Choice [1]: " choice
    choice=${choice:-1}

    case "$choice" in
        1)
            costa-keybinds mouse remap "$idx" button 2>/dev/null
            echo -e "${GREEN}✓ Set to passthrough — bind in Hyprland as mouse:$code${RESET}"
            ;;
        2)
            ratbagctl "$(ratbagctl list | cut -d: -f1)" button "$idx" action set special resolution-alternate 2>/dev/null
            echo -e "${GREEN}✓ Set to DPI shift${RESET}"
            ;;
        3)
            ratbagctl "$(ratbagctl list | cut -d: -f1)" button "$idx" action set special resolution-up 2>/dev/null
            echo -e "${GREEN}✓ Set to DPI cycle up${RESET}"
            ;;
        4)
            ratbagctl "$(ratbagctl list | cut -d: -f1)" button "$idx" action set special resolution-down 2>/dev/null
            echo -e "${GREEN}✓ Set to DPI cycle down${RESET}"
            ;;
        5)
            ratbagctl "$(ratbagctl list | cut -d: -f1)" button "$idx" action set special profile-cycle-up 2>/dev/null
            echo -e "${GREEN}✓ Set to profile cycle${RESET}"
            ;;
        6)
            echo -e "${DIM}No changes${RESET}"
            ;;
    esac
}

# ─── Main loop ───────────────────────────────────────────────
while true; do
    show_header
    show_current
    echo -e "${BOLD}Options:${RESET}"
    echo -e "  ${BOLD}d${RESET} — Detect & configure a button (press it to identify)"
    echo -e "  ${BOLD}r${RESET} — Refresh"
    echo -e "  ${BOLD}q${RESET} — Quit"
    echo ""
    read -rsn1 key

    case "$key" in
        d|D)
            echo ""
            detect_button
            echo ""
            echo -e "${DIM}Press any key to continue...${RESET}"
            read -rsn1
            ;;
        r|R) continue ;;
        q|Q) exit 0 ;;
    esac
done
