#!/bin/bash
# Toggle a terminal app as a dropdown panel
# Usage: toggle-app.sh <app-name> <command...>
# Window rules in hyprland.conf handle float/size/position

APP="$1"
shift
CMD="$*"
DROPDOWN_TITLE="dropdown-${APP}"

# Find window by initialTitle (stable even if app changes title)
ADDR=$(hyprctl clients -j | jq -r ".[] | select(.initialTitle == \"$DROPDOWN_TITLE\") | .address" 2>/dev/null | head -1)

if [ -n "$ADDR" ]; then
    # Window exists — close it
    hyprctl dispatch closewindow "address:$ADDR" 2>/dev/null
    # Clean up lock so next open works
    rm -f "/tmp/toggle-${DROPDOWN_TITLE}.lock"
else
    # No window — launch it
    LOCK="/tmp/toggle-${DROPDOWN_TITLE}.lock"
    exec 9>"$LOCK"
    flock -n 9 || { rm -f "$LOCK"; exec 9>"$LOCK"; flock -n 9 || exit 0; }

    TERM=""
    for t in ghostty foot kitty alacritty; do
        command -v "$t" &>/dev/null && TERM="$t" && break
    done
    case "$TERM" in
        ghostty)   ghostty --title="$DROPDOWN_TITLE" -e $CMD &disown ;;
        foot)      foot -T "$DROPDOWN_TITLE" $CMD &disown ;;
        kitty)     kitty -T "$DROPDOWN_TITLE" $CMD &disown ;;
        alacritty) alacritty -t "$DROPDOWN_TITLE" -e $CMD &disown ;;
    esac
    # Wait for window to appear (window rules handle positioning)
    for i in $(seq 1 20); do
        ADDR=$(hyprctl clients -j | jq -r ".[] | select(.initialTitle == \"$DROPDOWN_TITLE\") | .address" 2>/dev/null | head -1)
        [ -n "$ADDR" ] && break
        sleep 0.1
    done
fi
