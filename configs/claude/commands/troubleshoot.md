Run a Costa OS troubleshooting diagnostic.

Perform a comprehensive check of the system to identify and resolve issues.

## Step 1: Core system checks

Run all of these and collect results:

- `systemctl --failed` — failed system services
- `cat /sys/class/drm/card*/device/gpu_busy_percent` — GPU load
- `df -h /` — disk space
- `free -h` — memory usage
- `systemctl status ollama` — Ollama AI backend
- `systemctl --user status pipewire` — audio system

## Step 2: Desktop environment checks

- `hyprctl configerrors` — Hyprland config syntax errors
- Check if Waybar is running: `pgrep -x waybar`
- Check if wallpaper daemon is running: `pgrep -f wallpaper`
- Check if dunst is running: `pgrep -x dunst`

## Step 3: Recent errors

- `journalctl --user -p err --since "1 hour ago"` — user-level errors in the last hour
- `dmesg --level=err,warn | tail -20` — kernel-level errors and warnings

## Step 4: Diagnosis

Analyze all collected output and:

1. Clearly list each problem found, grouped by severity (critical, warning, informational).
2. For each problem, explain what it means and suggest a fix.
3. If the fix is safe and straightforward (e.g., restarting a crashed service, reloading a config), offer to apply it immediately.
4. If the fix is risky or destructive (e.g., removing packages, modifying fstab), explain the fix but ask for confirmation before proceeding.
5. If no issues are found, report "All systems healthy — no issues detected."

Use the costa-system MCP tools where available. Read relevant knowledge files via MCP resources before making changes.
