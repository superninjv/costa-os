#!/usr/bin/env bash
# Waybar module: workflow timer status
# Shows active timer count + next scheduled run

WORKFLOWS_DIR="$HOME/.config/costa/workflows"
TIMER_PREFIX="costa-flow-"

# Count active timers
ACTIVE=$(systemctl --user list-timers --no-pager --no-legend 2>/dev/null | grep "$TIMER_PREFIX" | wc -l)

if [ "$ACTIVE" -eq 0 ]; then
    echo '{"text": "", "tooltip": "No active workflow timers"}'
    exit 0
fi

# Get next scheduled run
NEXT=$(systemctl --user list-timers --no-pager --no-legend 2>/dev/null | grep "$TIMER_PREFIX" | head -1 | awk '{print $1, $2}')

# Build tooltip with all timers
TOOLTIP="Active workflow timers: $ACTIVE"
while IFS= read -r line; do
    timer_name=$(echo "$line" | awk '{print $NF}' | sed "s/${TIMER_PREFIX}//" | sed 's/\.timer//')
    next_run=$(echo "$line" | awk '{print $1, $2}')
    TOOLTIP="$TOOLTIP\n  $timer_name: $next_run"
done < <(systemctl --user list-timers --no-pager --no-legend 2>/dev/null | grep "$TIMER_PREFIX")

echo "{\"text\": \"⏱ $ACTIVE\", \"tooltip\": \"$TOOLTIP\", \"class\": \"active\"}"
