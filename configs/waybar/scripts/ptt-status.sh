#!/usr/bin/env bash
# Waybar custom module: push-to-talk status
# Outputs JSON for waybar with class for CSS styling

STATUS_FILE="/tmp/ptt-status"

while true; do
    if [ -f "$STATUS_FILE" ]; then
        STATE=$(cat "$STATUS_FILE")
    else
        STATE="ready"
    fi

    case "$STATE" in
        listening)
            echo '{"text": "󰍬", "tooltip": "Listening...", "class": "listening"}'
            ;;
        processing)
            echo '{"text": "󰍬", "tooltip": "Transcribing...", "class": "processing"}'
            ;;
        *)
            echo '{"text": "󰍬", "tooltip": "Push-to-talk ready (Super+Alt+V)", "class": "ready"}'
            ;;
    esac
    sleep 0.5
done
