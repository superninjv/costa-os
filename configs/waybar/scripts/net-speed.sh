#!/bin/bash
# Network throughput for waybar

iface=$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}' | head -1)
[ -z "$iface" ] && echo '{"text": "N/A", "tooltip": "No network"}' && exit 0

rx1=$(cat /sys/class/net/"$iface"/statistics/rx_bytes)
tx1=$(cat /sys/class/net/"$iface"/statistics/tx_bytes)
sleep 1
rx2=$(cat /sys/class/net/"$iface"/statistics/rx_bytes)
tx2=$(cat /sys/class/net/"$iface"/statistics/tx_bytes)

rx_rate=$(( (rx2 - rx1) ))
tx_rate=$(( (tx2 - tx1) ))

fmt() {
  local bytes=$1
  if [ "$bytes" -ge 1048576 ]; then
    awk "BEGIN {printf \"%.1fM\", $bytes/1048576}"
  elif [ "$bytes" -ge 1024 ]; then
    awk "BEGIN {printf \"%.0fK\", $bytes/1024}"
  else
    echo "${bytes}B"
  fi
}

rx=$(fmt "$rx_rate")
tx=$(fmt "$tx_rate")

echo "{\"text\": \"↓${rx} ↑${tx}\", \"tooltip\": \"$iface: ↓${rx}/s ↑${tx}/s\"}"
