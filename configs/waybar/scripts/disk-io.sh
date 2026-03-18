#!/bin/bash
# Disk I/O for waybar using iostat

io=$(iostat -d -y 1 1 2>/dev/null | awk '/^nvme/ {r+=$3; w+=$4} END {printf "%.0f %.0f", r, w}')
read_kb=$(echo "$io" | awk '{print $1}')
write_kb=$(echo "$io" | awk '{print $2}')

# Format human-readable
fmt() {
  local kb=$1
  if [ "$kb" -ge 1024 ]; then
    awk "BEGIN {printf \"%.1fM\", $kb/1024}"
  else
    echo "${kb}K"
  fi
}

r=$(fmt "${read_kb:-0}")
w=$(fmt "${write_kb:-0}")

jq -nc --arg text "${r}↓ ${w}↑" --arg tooltip "Disk I/O: Read ${r}/s  Write ${w}/s" \
  '{text: $text, tooltip: $tooltip}'
