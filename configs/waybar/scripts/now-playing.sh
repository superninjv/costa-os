#!/bin/bash
# Enhanced now-playing with progress bar for waybar

status=$(playerctl status 2>/dev/null)
if [ "$status" = "No players found" ] || [ -z "$status" ] || [ "$status" = "Stopped" ]; then
  jq -nc '{text: "󰎆 Music", tooltip: "Click to open music player", class: "idle"}'
  exit 0
fi

artist=$(playerctl metadata artist 2>/dev/null)
title=$(playerctl metadata title 2>/dev/null)
player=$(playerctl metadata --format '{{playerName}}' 2>/dev/null)
position=$(playerctl position 2>/dev/null | awk '{printf "%d", $1}')
length=$(playerctl metadata mpris:length 2>/dev/null)

# Convert microseconds to seconds
if [ -n "$length" ] && [ "$length" -gt 0 ]; then
  length_s=$((length / 1000000))
else
  length_s=0
fi

# Format time
fmt_time() {
  local s=$1
  printf "%d:%02d" $((s / 60)) $((s % 60))
}

# Progress bar
bar=""
if [ "$length_s" -gt 0 ] && [ -n "$position" ]; then
  pct=$((position * 100 / length_s))
  filled=$((pct / 5))
  empty=$((20 - filled))
  bar=$(printf '▓%.0s' $(seq 1 $filled 2>/dev/null))$(printf '░%.0s' $(seq 1 $empty 2>/dev/null))
  time_str="$(fmt_time "$position") / $(fmt_time "$length_s")"
else
  time_str=""
fi

# Status icon
case "$status" in
  Playing) icon="󰏤" ;;
  Paused)  icon="" ;;
  *)       icon="" ;;
esac

# Player icon
case "$player" in
  spotify) picon="" ;;
  firefox*) picon="󰈹" ;;
  *) picon="󰎆" ;;
esac

# Build display text (truncate to ~55 chars)
display="$picon $artist — $title"
display="${display:0:55}"

# Build tooltip
tooltip="$player: $artist — $title"
[ -n "$bar" ] && tooltip="$tooltip
$bar  $time_str"

jq -nc --arg text "$icon $display" --arg tooltip "$tooltip" --arg class "$player" \
  '{text: $text, tooltip: $tooltip, class: $class}'
