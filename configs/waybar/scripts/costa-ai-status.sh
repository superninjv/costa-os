#!/usr/bin/env bash
# Waybar module: voice-claude live status with animations

STATUS_FILE="/tmp/ptt-voice-status"
CMD_FILE="/tmp/ptt-voice-command"
LINE_FILE="/tmp/ptt-voice-lastline"
OUTPUT_FILE="/tmp/ptt-voice-output"
SCROLL_FILE="/tmp/ptt-voice-scroll"

SPINNER=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
FRAME=0
SCROLL_POS=0
MAX_DISPLAY=60

emit() {
  jq -nc --arg text "$1" --arg tooltip "$2" --arg class "$3" \
    '{text: $text, tooltip: $tooltip, class: $class}'
}

while true; do
    STATE=$(cat "$STATUS_FILE" 2>/dev/null || echo "idle")
    CMD=$(cat "$CMD_FILE" 2>/dev/null | head -c 50)
    LASTLINE=$(cat "$LINE_FILE" 2>/dev/null | head -c 60)
    MODEL=$(cat /tmp/ptt-voice-model 2>/dev/null | tr -d '[:space:]')
    MODEL_TAG=""
    [ -n "$MODEL" ] && MODEL_TAG="[$MODEL] "

    S=${SPINNER[$((FRAME % ${#SPINNER[@]}))]}
    FRAME=$((FRAME + 1))

    case "$STATE" in
        running)
            if [ -n "$LASTLINE" ]; then
                emit "$S ${MODEL_TAG}$LASTLINE" "Running: $CMD" "running"
            else
                emit "$S ${MODEL_TAG}$CMD" "Running: $CMD" "running"
            fi
            sleep 0.3
            ;;
        scroll)
            FULL=$(cat "$SCROLL_FILE" 2>/dev/null)
            FULL_LEN=${#FULL}
            if [ "$FULL_LEN" -le "$MAX_DISPLAY" ]; then
                emit " $FULL" "$FULL" "scroll"
                sleep 0.5
            else
                PADDED="$FULL     ·     $FULL"
                WINDOW="${PADDED:$SCROLL_POS:$MAX_DISPLAY}"
                emit " $WINDOW" "$FULL" "scroll"
                SCROLL_POS=$(( (SCROLL_POS + 1) % (FULL_LEN + 11) ))
                sleep 0.15
            fi
            ;;
        "timed out")
            emit "  timed out" "Command timed out: $CMD" "timedout"
            sleep 1
            ;;
        interactive)
            emit "$S  needs input" "Click to focus — Claude needs clarification
$CMD" "interactive"
            sleep 0.3
            ;;
        done)
            SUMMARY=$(head -3 "$OUTPUT_FILE" 2>/dev/null | tr '\n' ' ' | head -c 60)
            emit " $SUMMARY" "Click to view full output" "done"
            sleep 1
            ;;
        *)
            SCROLL_POS=0
            emit "󱜙 Costa" "Voice assistant ready (Super+Alt+V)
Click: open panel  |  Right-click: last output" "idle"
            sleep 1
            ;;
    esac
done
