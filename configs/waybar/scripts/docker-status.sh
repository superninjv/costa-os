#!/bin/bash
# Docker container count for waybar

if ! docker info &>/dev/null; then
  jq -nc '{text: "off", tooltip: "Docker daemon not running", class: "stopped"}'
  exit 0
fi

count=$(docker ps -q 2>/dev/null | wc -l)
total=$(docker ps -aq 2>/dev/null | wc -l)

if [ "$count" -eq 0 ]; then
  jq -nc --arg total "$total" \
    '{text: "0", tooltip: ("No running containers (" + $total + " total)"), class: "idle"}'
else
  names=$(docker ps --format '{{.Names}} ({{.Status}})' 2>/dev/null | head -10)
  jq -nc --arg text "$count" --arg tooltip "$names" \
    '{text: $text, tooltip: $tooltip, class: "running"}'
fi
