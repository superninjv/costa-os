#!/bin/bash
# SSH quick-connect via rofi

# Define your servers here — one per line, format: "Display Name|ssh command"
# Example: "My Server|ssh user@my-server.com"
SERVERS=(
)

# Build rofi list
entries=""
for entry in "${SERVERS[@]}"; do
  name="${entry%%|*}"
  entries+="󰣀  $name\n"
done

# Also parse ~/.ssh/config for hosts
if [ -f ~/.ssh/config ]; then
  hosts=$(grep -i "^Host " ~/.ssh/config | awk '{print $2}' | grep -v '\*')
  for h in $hosts; do
    entries+="  $h\n"
  done
fi

choice=$(printf "$entries" | rofi -dmenu -p "SSH" -i -theme-str 'window {width: 350px;}')
[ -z "$choice" ] && exit 0

# Strip icon prefix
name=$(echo "$choice" | sed 's/^[^ ]* *//')

# Check if it's a predefined server
for entry in "${SERVERS[@]}"; do
  sname="${entry%%|*}"
  cmd="${entry##*|}"
  if [ "$name" = "$sname" ]; then
    ghostty -e bash -c "$cmd"
    exit 0
  fi
done

# Otherwise it's an SSH config host
ghostty -e ssh "$name"
