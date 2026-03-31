#!/usr/bin/env bash
# Supervise AGS shell — respawn on crash with exponential backoff
# Used by hyprland exec-once to keep the shell alive

command -v ags &>/dev/null || exit 0

AGS_DIR="${1:-$HOME/.config/ags}"
BACKOFF=1
MAX_BACKOFF=30
CRASH_LOG="/tmp/costa-ags-crashes.log"
AGS_PID=""

cleanup() {
  [ -n "$AGS_PID" ] && kill "$AGS_PID" 2>/dev/null
  exit 0
}
trap cleanup TERM INT HUP

# Kill any orphaned gjs from previous runs
pkill -f "gjs -m /run/user/.*/ags.js" 2>/dev/null
sleep 0.5

while true; do
  START_TIME=$(date +%s)

  # Run AGS in background so we can track its PID
  ags run -d "$AGS_DIR" >> /tmp/costa-ags.log 2>&1 &
  AGS_PID=$!
  wait "$AGS_PID"
  EXIT=$?
  AGS_PID=""

  END_TIME=$(date +%s)
  RUNTIME=$(( END_TIME - START_TIME ))

  # Clean exit (ags quit, code 0) — don't respawn
  [ $EXIT -eq 0 ] && break

  # Kill orphaned gjs in case ags wrapper died but gjs lingered
  pkill -f "gjs -m /run/user/.*/ags.js" 2>/dev/null
  sleep 0.5

  TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$TIMESTAMP] AGS exited ($EXIT) after ${RUNTIME}s, restarting in ${BACKOFF}s" >> "$CRASH_LOG"

  sleep "$BACKOFF"

  # Reset backoff if AGS ran for more than 60s (real crash vs startup loop)
  if [ $RUNTIME -gt 60 ]; then
    BACKOFF=1
  else
    BACKOFF=$(( BACKOFF * 2 ))
    [ $BACKOFF -gt $MAX_BACKOFF ] && BACKOFF=$MAX_BACKOFF
  fi
done
