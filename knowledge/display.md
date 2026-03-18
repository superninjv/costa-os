---
l0: "Display management: brightness, night light, monitor resolution, refresh rate, scaling, rotation"
l1_sections: ["Brightness", "Night Light / Blue Light Filter", "Monitor Management", "Refresh Rate", "Scaling", "Rotation"]
tags: [brightness, night-light, gamma, monitor, resolution, refresh-rate, scale, rotate, hdmi, displayport]
---

# Display & Brightness

## Brightness
- Get current: `brightnessctl get` (raw value), `brightnessctl info` (percentage)
- Set percentage: `brightnessctl set 50%`
- Increase: `brightnessctl set +10%`
- Decrease: `brightnessctl set 10%-`
- Max brightness: `brightnessctl set 100%`
- Min (not off): `brightnessctl set 1%`

## Night Light / Blue Light Filter
- Using gammastep: `gammastep -O 4500` (set color temp in Kelvin, lower = warmer)
- Auto day/night: `gammastep -l LATITUDE:LONGITUDE` (auto adjusts by time)
- Reset to normal: `killall gammastep` or `gammastep -O 6500`
- Install: `pacman -S gammastep`

## Monitor Management
- List monitors: `hyprctl monitors`
- Monitor config file: `~/.config/hypr/monitors.conf`
- Set resolution: `hyprctl keyword monitor DP-1,2560x1440@165,auto,1`
- Disable monitor: `hyprctl keyword monitor HDMI-A-2,disable`
- Enable monitor: `hyprctl keyword monitor HDMI-A-2,preferred,auto,1`
- Mirror monitors: `hyprctl keyword monitor HDMI-A-2,preferred,auto,1,mirror,DP-1`

## Refresh Rate
- Set specific: `hyprctl keyword monitor DP-1,2560x1440@144,auto,1`
- Check current: `hyprctl monitors -j | jq '.[].refreshRate'`

## Scaling
- Set scale: `hyprctl keyword monitor DP-1,preferred,auto,1.5` (1.5x scale)
- HiDPI: use scale 2 for 4K monitors

## Rotation
- Rotate: `hyprctl keyword monitor HDMI-A-1,preferred,auto,1,transform,1`
- Values: 0=normal, 1=90°, 2=180°, 3=270°, 4=flipped, 5=flipped+90°, 6=flipped+180°, 7=flipped+270°
