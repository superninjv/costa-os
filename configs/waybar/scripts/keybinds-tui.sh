#!/bin/bash
# TUI keybind viewer for dropdown panel
# Shows keybinds and mouse buttons, filterable with /

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
COSTA_KEYBINDS="$HOME/projects/costa-os/ai-router/costa-keybinds"

# Colors
BOLD='\033[1m'
DIM='\033[2m'
CYAN='\033[36m'
WARM='\033[38;2;194;120;73m'
GREEN='\033[32m'
YELLOW='\033[33m'
RESET='\033[0m'

show_keybinds() {
    echo -e "${BOLD}${CYAN} Keybinds${RESET}  ${DIM}(q=quit  /=filter  m=mouse  a=add)${RESET}"
    echo -e "${DIM}$(printf '─%.0s' {1..70})${RESET}"
    echo ""
    "$COSTA_KEYBINDS" list "$@" 2>/dev/null
}

show_mouse() {
    echo -e "${BOLD}${CYAN}󰍽 Mouse Buttons${RESET}  ${DIM}(q=quit  k=keybinds  e=enable-all  d=detect)${RESET}"
    echo -e "${DIM}$(printf '─%.0s' {1..70})${RESET}"
    echo ""
    "$COSTA_KEYBINDS" mouse 2>/dev/null
}

mode="keybinds"
filter=""

while true; do
    clear
    if [ "$mode" = "keybinds" ]; then
        if [ -n "$filter" ]; then
            show_keybinds --filter "$filter"
            echo ""
            echo -e "${DIM}Filter: ${YELLOW}${filter}${RESET}  ${DIM}(Esc=clear)${RESET}"
        else
            show_keybinds
        fi
    elif [ "$mode" = "mouse" ]; then
        show_mouse
        echo ""
        echo -e "  ${BOLD}c${RESET} — Configure buttons (detect & remap)"
    elif [ "$mode" = "detect" ]; then
        echo -e "${BOLD}${CYAN}󰍽 Button Detection${RESET}"
        echo -e "${DIM}$(printf '─%.0s' {1..70})${RESET}"
        echo ""
        echo -e "Press any extra mouse button..."
        echo ""
        "$COSTA_KEYBINDS" mouse detect 2>/dev/null
        echo ""
        echo -e "${DIM}Press any key to go back${RESET}"
        read -rsn1
        mode="mouse"
        continue
    fi

    echo ""
    read -rsn1 key

    case "$key" in
        q) exit 0 ;;
        m) mode="mouse"; filter="" ;;
        k) mode="keybinds"; filter="" ;;
        e)
            if [ "$mode" = "mouse" ]; then
                echo ""
                "$COSTA_KEYBINDS" mouse enable-all 2>/dev/null
                echo ""
                echo -e "${DIM}Press any key to continue${RESET}"
                read -rsn1
            fi
            ;;
        d)
            if [ "$mode" = "mouse" ]; then
                mode="detect"
            fi
            ;;
        c)
            if [ "$mode" = "mouse" ]; then
                ~/.config/waybar/scripts/mouse-mapper.sh
            fi
            ;;
        a)
            if [ "$mode" = "keybinds" ]; then
                echo ""
                echo -ne "${WARM}Mods${RESET} (e.g. SUPER, SUPER SHIFT): "
                read -r mods
                echo -ne "${WARM}Key${RESET} (e.g. F1, mouse:275): "
                read -r key_name
                echo -ne "${WARM}Action${RESET} (e.g. exec firefox): "
                read -r action
                dispatcher=$(echo "$action" | cut -d' ' -f1)
                args=$(echo "$action" | cut -d' ' -f2-)
                [ "$args" = "$dispatcher" ] && args=""
                echo ""
                "$COSTA_KEYBINDS" add "$mods" "$key_name" "$dispatcher" "$args" 2>/dev/null
                echo ""
                echo -e "${DIM}Press any key to continue${RESET}"
                read -rsn1
            fi
            ;;
        /)
            if [ "$mode" = "keybinds" ]; then
                echo -ne "\n${WARM}Filter: ${RESET}"
                read -r filter
            fi
            ;;
        $'\x1b')
            filter=""
            ;;
    esac
done
