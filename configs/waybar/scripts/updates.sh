#!/bin/bash
# System update count for waybar

count=$(checkupdates 2>/dev/null | wc -l)
aur_count=$(yay -Qua 2>/dev/null | wc -l)
total=$((count + aur_count))

if [ "$total" -eq 0 ]; then
  echo '{"text": "", "tooltip": "System up to date", "class": "uptodate"}'
else
  echo "{\"text\": \"$total\", \"tooltip\": \"$count official + $aur_count AUR updates\", \"class\": \"pending\"}"
fi
