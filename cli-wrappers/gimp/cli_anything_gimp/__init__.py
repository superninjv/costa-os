"""CLI-Anything wrapper for GIMP — deterministic CLI access to GIMP editor state.

Uses GIMP's Script-Fu IPC socket when available, falls back to parsing
Hyprland window titles and reading GIMP config files for state.

Capabilities: status, open images, recent files, current tool, export
"""

__version__ = "0.1.0"
