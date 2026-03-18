#!/usr/bin/env bash
# Voice Claude click handler
# Short responses: notification + clipboard (no window steal)
# Long responses or running: open viewer window
# Idle: open text input

STATUS=$(cat /tmp/ptt-voice-status 2>/dev/null || echo "idle")
OUTPUT_FILE="/tmp/ptt-voice-output"

# If interactive window exists, focus it
if hyprctl clients -j | jq -e '.[] | select(.class == "voice-claude")' >/dev/null 2>&1; then
    hyprctl dispatch focuswindow class:voice-claude
    exit 0
fi

# Idle: open text input
if [ "$STATUS" = "idle" ]; then
    ~/.config/waybar/voice-claude-input.sh
    exit 0
fi

# Running: open viewer
if [ "$STATUS" = "running" ]; then
    ghostty --class=voice-output -e ~/.config/waybar/voice-claude-viewer.sh
    exit 0
fi

# Has output: check length
if [ -s "$OUTPUT_FILE" ]; then
    OUTPUT=$(cat "$OUTPUT_FILE")
    CHAR_COUNT=${#OUTPUT}
    LINE_COUNT=$(echo "$OUTPUT" | wc -l)

    if [ "$CHAR_COUNT" -lt 300 ] && [ "$LINE_COUNT" -lt 6 ]; then
        # Short response: notification + clipboard, no window
        echo "$OUTPUT" | wl-copy
        notify-send -t 8000 "󰗊 Voice Response" "$OUTPUT" -a "VoiceMode"
    else
        # Long response: open viewer
        ghostty --class=voice-output -e ~/.config/waybar/voice-claude-viewer.sh
    fi
else
    # Scroll/done state but no output
    ~/.config/waybar/voice-claude-input.sh
fi
