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

while true; do
    STATE=$(cat "$STATUS_FILE" 2>/dev/null || echo "idle")
    CMD=$(cat "$CMD_FILE" 2>/dev/null | tr -d '"\\' | head -c 50)
    LASTLINE=$(cat "$LINE_FILE" 2>/dev/null | tr -d '"\\' | head -c 60)
    MODEL=$(cat /tmp/ptt-voice-model 2>/dev/null | tr -d '[:space:]')
    MODEL_TAG=""
    [ -n "$MODEL" ] && MODEL_TAG="[$MODEL] "

    S=${SPINNER[$((FRAME % ${#SPINNER[@]}))]}
    FRAME=$((FRAME + 1))

    case "$STATE" in
        running)
            if [ -n "$LASTLINE" ]; then
                echo "{\"text\": \"$S ${MODEL_TAG}$LASTLINE\", \"tooltip\": \"Running: $CMD\", \"class\": \"running\"}"
            else
                echo "{\"text\": \"$S ${MODEL_TAG}$CMD\", \"tooltip\": \"Running: $CMD\", \"class\": \"running\"}"
            fi
            sleep 0.3
            ;;
        scroll)
            # Smooth scrolling response text
            FULL=$(cat "$SCROLL_FILE" 2>/dev/null | tr -d '"\\')
            FULL_LEN=${#FULL}
            if [ "$FULL_LEN" -le "$MAX_DISPLAY" ]; then
                # Short enough to show fully
                echo "{\"text\": \" $FULL\", \"tooltip\": \"$FULL\", \"class\": \"scroll\"}"
                sleep 0.5
            else
                # Scroll with padding for smooth wrap
                PADDED="$FULL     ·     $FULL"
                WINDOW="${PADDED:$SCROLL_POS:$MAX_DISPLAY}"
                echo "{\"text\": \" $WINDOW\", \"tooltip\": \"$FULL\", \"class\": \"scroll\"}"
                SCROLL_POS=$(( (SCROLL_POS + 1) % (FULL_LEN + 11) ))
                sleep 0.15
            fi
            ;;
        "timed out")
            echo "{\"text\": \"  timed out\", \"tooltip\": \"Command timed out: $CMD\", \"class\": \"timedout\"}"
            sleep 1
            ;;
        interactive)
            echo "{\"text\": \"$S  needs input\", \"tooltip\": \"Click to focus — Claude needs clarification\\n$CMD\", \"class\": \"interactive\"}"
            sleep 0.3
            ;;
        done)
            SUMMARY=$(head -3 "$OUTPUT_FILE" 2>/dev/null | tr -d '"\\' | tr '\n' ' ' | head -c 60)
            echo "{\"text\": \" $SUMMARY\", \"tooltip\": \"Click to view full output\", \"class\": \"done\"}"
            sleep 1
            ;;
        *)
            SCROLL_POS=0
            echo "{\"text\": \"󰗊\", \"tooltip\": \"Voice Claude ready (Super+Alt+V)\", \"class\": \"idle\"}"
            sleep 1
            ;;
    esac
done
