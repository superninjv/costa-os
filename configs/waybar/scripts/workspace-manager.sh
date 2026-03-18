#!/usr/bin/env bash
# Workspace manager — rofi menu for workspace operations

WORKSPACE_ID="$1"

# Get current workspace info
current_ws=$(hyprctl activeworkspace -j | jq -r '.id')
all_ws=$(hyprctl workspaces -j | jq -r '.[].id' | sort -n | grep -v '^-')
ws_clients=$(hyprctl clients -j | jq -r --arg ws "$WORKSPACE_ID" '[.[] | select(.workspace.id == ($ws | tonumber))] | length')

# Build menu
options="  Move focused window here
  Swap with current workspace
  Move all windows here
󰁁  Move all windows away"

if [ "$ws_clients" -eq 0 ] && [ "$WORKSPACE_ID" != "$current_ws" ]; then
    options="$options
󰆴  Remove workspace"
fi

options="$options
  New workspace
  Rename workspace"

choice=$(echo "$options" | rofi -dmenu -p "Workspace $WORKSPACE_ID" -theme-str 'window {width: 320px;}' 2>/dev/null)

case "$choice" in
    *"Move focused window here"*)
        hyprctl dispatch movetoworkspace "$WORKSPACE_ID"
        ;;
    *"Swap with current workspace"*)
        hyprctl dispatch swapactiveworkspaces "$current_ws" "$WORKSPACE_ID" 2>/dev/null
        # If not on same monitor, move windows manually
        ;;
    *"Move all windows here"*)
        hyprctl clients -j | jq -r --arg ws "$current_ws" \
            '.[] | select(.workspace.id == ($ws | tonumber)) | .address' | \
            while read -r addr; do
                hyprctl dispatch movetoworkspacesilent "$WORKSPACE_ID,address:$addr"
            done
        ;;
    *"Move all windows away"*)
        # Move all windows from target workspace to current
        hyprctl clients -j | jq -r --arg ws "$WORKSPACE_ID" \
            '.[] | select(.workspace.id == ($ws | tonumber)) | .address' | \
            while read -r addr; do
                hyprctl dispatch movetoworkspacesilent "$current_ws,address:$addr"
            done
        ;;
    *"Remove workspace"*)
        # Focus it then move away — Hyprland auto-removes empty workspaces
        notify-send "Workspace $WORKSPACE_ID" "Removed (empty workspace)"
        ;;
    *"New workspace"*)
        # Find next available ID
        next_id=1
        while echo "$all_ws" | grep -qx "$next_id"; do
            ((next_id++))
        done
        hyprctl dispatch workspace "$next_id"
        notify-send "Workspace" "Created workspace $next_id"
        ;;
    *"Rename workspace"*)
        new_name=$(rofi -dmenu -p "New name for workspace $WORKSPACE_ID" -theme-str 'window {width: 320px;}' 2>/dev/null)
        if [ -n "$new_name" ]; then
            hyprctl dispatch renameworkspace "$WORKSPACE_ID" "$new_name"
        fi
        ;;
esac
