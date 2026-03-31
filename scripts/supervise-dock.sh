#!/usr/bin/env bash
# Supervise nwg-dock-hyprland — respawn on crash with backoff
# Used by hyprland exec-once to keep the dock alive across crashes

command -v nwg-dock-hyprland &>/dev/null || exit 0

BACKOFF=1
MAX_BACKOFF=30

while true; do
  nwg-dock-hyprland -d -f -i 48 -mb 6 -ml 0 -mr 0 -hd 0
  EXIT=$?

  # Clean exit (user killed it intentionally) — don't respawn
  [ $EXIT -eq 0 ] && break

  echo "[costa] nwg-dock-hyprland exited ($EXIT), restarting in ${BACKOFF}s..." >&2
  sleep "$BACKOFF"
  BACKOFF=$(( BACKOFF * 2 ))
  [ $BACKOFF -gt $MAX_BACKOFF ] && BACKOFF=$MAX_BACKOFF
done
