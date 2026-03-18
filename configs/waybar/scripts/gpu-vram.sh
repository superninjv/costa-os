#!/bin/bash
# GPU VRAM usage for waybar (AMD)

vram_used=$(cat /sys/class/drm/card1/device/mem_info_vram_used 2>/dev/null)
vram_total=$(cat /sys/class/drm/card1/device/mem_info_vram_total 2>/dev/null)

if [ -z "$vram_used" ] || [ -z "$vram_total" ]; then
  jq -nc '{text: "N/A", tooltip: "VRAM info unavailable"}'
  exit 0
fi

used_mb=$((vram_used / 1048576))
total_mb=$((vram_total / 1048576))
used_gb=$(awk "BEGIN {printf \"%.1f\", $used_mb/1024}")
total_gb=$(awk "BEGIN {printf \"%.1f\", $total_mb/1024}")
pct=$((used_mb * 100 / total_mb))

jq -nc --arg text "${used_gb}G" --arg tooltip "VRAM: ${used_gb}G / ${total_gb}G (${pct}%)" \
  '{text: $text, tooltip: $tooltip, class: "normal"}'
