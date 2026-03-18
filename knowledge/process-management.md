---
l0: "Process and system management: finding/killing processes, resources, shutdown, suspend"
l1_sections: ["Find Processes", "Kill Processes", "System Resources", "Uptime & Boot", "Shutdown / Reboot", "Scheduled Tasks"]
tags: [process, kill, cpu, ram, memory, htop, bottom, shutdown, reboot, suspend, uptime, temperature]
---

# Process & System Management

## Find Processes
- By name: `pgrep -f processname` or `procs processname`
- What's using CPU: `procs --sortd cpu` or `ps aux --sort=-%cpu | head -20`
- What's using RAM: `procs --sortd mem` or `ps aux --sort=-%mem | head -20`
- Interactive: `btm` (bottom) or `htop`
- Full process tree: `procs --tree`

## Kill Processes
- By name: `pkill -f processname`
- By PID: `kill PID`
- Force kill: `kill -9 PID` or `pkill -9 -f processname`
- Kill frozen window: `hyprctl dispatch killactive` (focused window)
- Kill by window class: `hyprctl dispatch closewindow class:appname`

## System Resources
- CPU/RAM/swap overview: `btm` or `htop`
- Memory: `free -h`
- CPU info: `lscpu`
- Disk space: `df -h`
- Disk usage per dir: `dust /path` or `du -sh /path/*`
- GPU usage: `cat /sys/class/drm/card*/device/gpu_busy_percent` (AMD)
- GPU VRAM: `cat /sys/class/drm/card*/device/mem_info_vram_used` (AMD)
- Temperature: `sensors` (if lm_sensors installed)
- System overview: `fastfetch`

## Uptime & Boot
- Uptime: `uptime`
- Last boot: `who -b`
- Boot log: `journalctl -b`
- Previous boot: `journalctl -b -1`

## Shutdown / Reboot
- Reboot: `reboot` or `systemctl reboot`
- Shutdown: `poweroff` or `systemctl poweroff`
- Suspend: `systemctl suspend`
- Lock screen: `hyprlock` or `loginctl lock-session`

## Scheduled Tasks
- List timers: `systemctl list-timers --all`
- Cron jobs: `crontab -l`
- Edit cron: `crontab -e`
