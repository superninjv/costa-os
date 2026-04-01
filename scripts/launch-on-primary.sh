#!/bin/bash
# Launch an app on the primary monitor, then restore focus.
# Usage: launch-on-primary.sh <command...>
# Reads PRIMARY_MONITOR from env, defaults to DP-1, falls back to first non-headless monitor.

PRIMARY="${COSTA_PRIMARY_MONITOR:-DP-1}"

# Detect primary if not set — first non-headless, non-portrait monitor
if ! hyprctl monitors -j 2>/dev/null | jq -e ".[] | select(.name == \"$PRIMARY\")" >/dev/null 2>&1; then
    PRIMARY=$(hyprctl monitors -j | jq -r '[.[] | select(.name | startswith("HEADLESS") | not)] | .[0].name')
fi

CURRENT=$(hyprctl activeworkspace -j | jq -r '.monitor')

hyprctl dispatch focusmonitor "$PRIMARY"
hyprctl dispatch exec -- "$*"

if [ "$CURRENT" != "$PRIMARY" ]; then
    sleep 0.1
    hyprctl dispatch focusmonitor "$CURRENT"
fi
