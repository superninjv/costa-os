#!/bin/bash
# Connectivity status for waybar — gauge icon with hover details
# All numbers hidden behind icon; tooltip shows speed, updates, bluetooth

# Network speed
iface=$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}' | head -1)
if [ -n "$iface" ]; then
  rx1=$(cat /sys/class/net/"$iface"/statistics/rx_bytes 2>/dev/null)
  tx1=$(cat /sys/class/net/"$iface"/statistics/tx_bytes 2>/dev/null)
  sleep 1
  rx2=$(cat /sys/class/net/"$iface"/statistics/rx_bytes 2>/dev/null)
  tx2=$(cat /sys/class/net/"$iface"/statistics/tx_bytes 2>/dev/null)
  rx_rate=$(( rx2 - rx1 ))
  tx_rate=$(( tx2 - tx1 ))

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
  net_tip="$iface: ↓${rx}/s  ↑${tx}/s"
  connected=true
else
  net_tip="No network connection"
  connected=false
fi

# Update count (cached — don't run checkupdates every 5s)
UPDATE_CACHE="/tmp/waybar-update-count"
if [ ! -f "$UPDATE_CACHE" ] || [ $(( $(date +%s) - $(stat -c %Y "$UPDATE_CACHE" 2>/dev/null || echo 0) )) -gt 3600 ]; then
  total=$(( $(checkupdates 2>/dev/null | wc -l) + $(yay -Qua 2>/dev/null | wc -l) ))
  echo "$total" > "$UPDATE_CACHE"
fi
updates=$(cat "$UPDATE_CACHE" 2>/dev/null || echo 0)
update_tip="Updates: $updates available"

# Bluetooth
bt_powered=$(bluetoothctl show 2>/dev/null | grep "Powered:" | awk '{print $2}')
bt_connected=$(bluetoothctl devices Connected 2>/dev/null | wc -l)
bt_tip="Bluetooth: $bt_powered"
[ "$bt_connected" -gt 0 ] && bt_tip="Bluetooth: $bt_powered ($bt_connected connected)"

# Build tooltip
tooltip="$net_tip
$update_tip
$bt_tip

Click for options"

# Icon + class
if [ "$connected" = true ]; then
  icon="󰛳"
  class="active"
else
  icon="󰛵"
  class="disconnected"
fi

# Badge: small icons only, no numbers in the bar
badge=""
[ "$updates" -gt 0 ] && badge+=" 󰁝"
[ "$bt_connected" -gt 0 ] && badge+=" "

jq -nc --arg text "$icon$badge" --arg tooltip "$tooltip" --arg class "$class" \
  '{text: $text, tooltip: $tooltip, class: $class}'
