#!/usr/bin/env bash
# Voice Claude output viewer with loading animation

STATUS_FILE="/tmp/ptt-voice-status"
OUTPUT_FILE="/tmp/ptt-voice-output"
CMD_FILE="/tmp/ptt-voice-command"

CMD=$(cat "$CMD_FILE" 2>/dev/null || echo "")
STATE=$(cat "$STATUS_FILE" 2>/dev/null || echo "idle")

echo -e "\033[1;36m󰗊 Voice Claude\033[0m"
echo -e "\033[0;90m$CMD\033[0m"
echo "───────────────────────────────────────"
echo ""

if [ "$STATE" = "running" ]; then
    # Animated loading while waiting for output
    FRAMES=("    ⠁ " "    ⠂ " "    ⠄ " "    ⡀ " "    ⠄ " "    ⠂ " "    ⠁ " "    ⠈ " "    ⠐ " "    ⠠ ")
    DOTS=("⣾" "⣽" "⣻" "⢿" "⡿" "⣟" "⣯" "⣷")

    echo -e "\033[0;90mWaiting for Claude...\033[0m"
    echo ""

    i=0
    while [ "$(cat "$STATUS_FILE" 2>/dev/null)" = "running" ]; do
        d=${DOTS[$((i % ${#DOTS[@]}))]}
        printf "\r  \033[1;36m%s\033[0m  \033[0;90mthinking...\033[0m  " "$d"
        i=$((i + 1))
        sleep 0.15
    done
    printf "\r                              \r"
    echo ""
fi

# Show output
if [ -s "$OUTPUT_FILE" ]; then
    cat "$OUTPUT_FILE"
else
    echo -e "\033[0;90mNo output.\033[0m"
fi

echo ""
echo "───────────────────────────────────────"
STATE=$(cat "$STATUS_FILE" 2>/dev/null || echo "idle")
if [ "$STATE" = "done" ]; then
    echo -e "\033[1;32m Done\033[0m"
elif [ "$STATE" = "interactive" ]; then
    echo -e "\033[1;33m Needs input — see interactive window\033[0m"
fi
echo ""
read -n1 -p "Press any key to close"
