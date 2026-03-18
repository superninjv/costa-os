---
l0: "Hyprland window manager: hyprctl commands, config syntax, window rules, monitor management, touchscreen"
l1_sections: ["Window Management", "Moving Windows Between Monitors", "Launching Apps on a Specific Monitor", "How to figure out which monitor is \"top\", \"left\", etc.", "Workspace", "Query", "Config (hyprland.conf)", "Window Rules", "Touchscreen & Touch Gestures"]
tags: [hyprland, hyprctl, window, workspace, monitor, dispatch, float, tile, rule, touchscreen, gesture]
---
# Hyprland Quick Reference

## Window Management
- `hyprctl dispatch exec [command]` — launch program
- `hyprctl dispatch killactive` — close focused window
- `hyprctl dispatch togglefloating` — toggle float
- `hyprctl dispatch fullscreen 0|1|2` — fullscreen (0=full, 1=maximize, 2=no gaps)
- `hyprctl dispatch movewindow l|r|u|d` — move in direction
- `hyprctl dispatch resizeactive X Y` — resize by pixels
- `hyprctl dispatch focuswindow class:name` — focus by class
- `hyprctl dispatch movetoworkspace N` — move to workspace
- `hyprctl dispatch movetoworkspacesilent N` — move without following

## Moving Windows Between Monitors
- `hyprctl dispatch movewindow mon:MONITOR_NAME` — move focused window to a specific monitor
- `hyprctl dispatch movecurrentworkspacetomonitor MONITOR_NAME` — move entire workspace to monitor
- `hyprctl dispatch focusmonitor MONITOR_NAME` — focus a monitor
- To find monitor names and positions: `hyprctl monitors -j`
- Monitor positions are set in `~/.config/hypr/monitors.conf` or `hyprland.conf`

## Launching Apps on a Specific Monitor
To open an app on a particular monitor, use a workspace rule then launch:
1. Find which workspace is on the target monitor: `hyprctl monitors -j | jq '.[] | {name, activeWorkspace}'`
2. Move focus there, launch, then move back:
   ```
   hyprctl dispatch focusmonitor MONITOR_NAME && hyprctl dispatch exec [firefox] && sleep 0.5 && hyprctl dispatch focusmonitor DP-1
   ```
   Or use a temporary window rule:
   ```
   hyprctl keyword windowrulev2 "workspace 5,title:^()$,class:^(firefox)$" && hyprctl dispatch exec [firefox]
   ```

## How to figure out which monitor is "top", "left", etc.
Run `hyprctl monitors -j` and check the x,y positions:
- The monitor with the lowest y value is the TOP monitor
- The monitor with the lowest x value is the LEFT monitor
- The monitor with the largest x value is the RIGHT monitor
- Compare y values — negative y = physically above, positive = below

## Workspace
- `hyprctl dispatch workspace N` — switch to workspace
- `hyprctl dispatch movetoworkspace special:name` — move to special/scratchpad
- Each workspace is bound to a monitor — moving a window to a workspace on another monitor moves it there

## Query
- `hyprctl monitors [-j]` — monitor info
- `hyprctl clients [-j]` — all windows
- `hyprctl activewindow [-j]` — focused window
- `hyprctl binds [-j]` — all keybinds
- `hyprctl configerrors` — check config
- `hyprctl reload` — reload config (no restart needed)

## Config (hyprland.conf)
- `monitor=name,WxH@Hz,position,scale`
- `bind=$mod,key,dispatcher,args`
- `exec-once=command` — run at startup
- `windowrulev2=rule,class:regex` — per-window rules
- `env=VAR,value` — doesn't support inline `VAR=val cmd`, wrap in `bash -c`

## Window Rules
- `float,class:^(rofi|pavucontrol)$`
- `opacity 0.9,class:^(ghostty)$`
- `workspace 5,class:^(firefox)$`
- `size 800 600,class:^(calculator)$`

## Touchscreen & Touch Gestures
- Touch input configured via `~/.config/hypr/touch.conf` (sourced from hyprland.conf)
- **hyprgrass** plugin provides multi-touch gestures (swipe, long press)
- **squeekboard** provides on-screen keyboard (window rule: float, pin, slide from bottom)
- Both are hardware-gated — only configured if a touchscreen is detected during first-boot
