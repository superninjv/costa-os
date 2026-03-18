Run a Costa OS system health check.

Follow these steps to assess system health:

1. Read the current screen state using the `read_screen` MCP tool to understand what the user is looking at.

2. Check for failed systemd services:
   ```
   systemctl --failed
   ```

3. Check GPU utilization:
   ```
   cat /sys/class/drm/card*/device/gpu_busy_percent
   ```

4. Check disk space on the root partition:
   ```
   df -h /
   ```

5. Check memory usage:
   ```
   free -h
   ```

6. Check if Ollama is running and healthy:
   ```
   systemctl status ollama
   ```

7. Check PipeWire audio status:
   ```
   systemctl --user status pipewire
   ```

After running all checks, summarize the results. If everything looks good, report "All systems healthy." If any issues are found, clearly list each problem with a suggested fix.

Use the costa-system MCP tools where available.
