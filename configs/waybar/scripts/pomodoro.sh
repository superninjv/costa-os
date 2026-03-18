#!/bin/bash
# Pomodoro timer for waybar
# Click to start/stop, right-click to reset

STATEFILE="/tmp/waybar-pomodoro"
WORK_MIN=25
BREAK_MIN=5

action="${1:-status}"

case "$action" in
  toggle)
    if [ -f "$STATEFILE" ]; then
      state=$(jq -r '.state' "$STATEFILE")
      if [ "$state" = "running" ] || [ "$state" = "break" ]; then
        jq '.state = "paused"' "$STATEFILE" > "${STATEFILE}.tmp" && mv "${STATEFILE}.tmp" "$STATEFILE"
      elif [ "$state" = "paused" ]; then
        # Adjust start time to account for pause
        paused_at=$(jq -r '.paused_at // 0' "$STATEFILE")
        now=$(date +%s)
        elapsed_pause=$((now - paused_at))
        start=$(jq -r '.start' "$STATEFILE")
        new_start=$((start + elapsed_pause))
        jq --arg s "$new_start" '.state = "running" | .start = ($s | tonumber)' "$STATEFILE" > "${STATEFILE}.tmp" && mv "${STATEFILE}.tmp" "$STATEFILE"
      else
        # Start new session
        echo "{\"state\": \"running\", \"start\": $(date +%s), \"duration\": $((WORK_MIN * 60))}" > "$STATEFILE"
      fi
    else
      echo "{\"state\": \"running\", \"start\": $(date +%s), \"duration\": $((WORK_MIN * 60))}" > "$STATEFILE"
    fi
    ;;

  reset)
    rm -f "$STATEFILE"
    ;;

  status)
    if [ ! -f "$STATEFILE" ]; then
      echo '{"text": "󰔟", "tooltip": "Click to start pomodoro (25m)", "class": "idle"}'
      exit 0
    fi

    state=$(jq -r '.state' "$STATEFILE")
    start=$(jq -r '.start' "$STATEFILE")
    duration=$(jq -r '.duration' "$STATEFILE")
    now=$(date +%s)
    elapsed=$((now - start))
    remaining=$((duration - elapsed))

    if [ "$state" = "paused" ]; then
      paused_at=$(jq -r '.paused_at // empty' "$STATEFILE")
      if [ -z "$paused_at" ]; then
        jq --arg t "$now" '.paused_at = ($t | tonumber)' "$STATEFILE" > "${STATEFILE}.tmp" && mv "${STATEFILE}.tmp" "$STATEFILE"
      fi
      elapsed_before=$((${paused_at:-$now} - start))
      remaining=$((duration - elapsed_before))
      min=$((remaining / 60))
      sec=$((remaining % 60))
      printf '{"text": "󰏤 %02d:%02d", "tooltip": "Paused — click to resume", "class": "paused"}\n' "$min" "$sec"
    elif [ "$remaining" -le 0 ]; then
      if [ "$state" = "running" ]; then
        notify-send -u normal "Pomodoro" "Work session complete! Take a break." -i dialog-information
        echo "{\"state\": \"break\", \"start\": $(date +%s), \"duration\": $((BREAK_MIN * 60))}" > "$STATEFILE"
      elif [ "$state" = "break" ]; then
        notify-send -u normal "Pomodoro" "Break over! Ready for another round?" -i dialog-information
        rm -f "$STATEFILE"
      fi
      echo '{"text": "󰔟 Done!", "tooltip": "Session complete — click to restart", "class": "done"}'
    else
      min=$((remaining / 60))
      sec=$((remaining % 60))
      if [ "$state" = "break" ]; then
        printf '{"text": "☕ %02d:%02d", "tooltip": "Break time", "class": "break"}\n' "$min" "$sec"
      else
        printf '{"text": "󰔟 %02d:%02d", "tooltip": "Focus time — %d min remaining", "class": "running"}\n' "$min" "$sec" "$min"
      fi
    fi
    ;;
esac
