---
l0: "Claude Code integration: launching, custom commands, MCP tools, virtual monitor, configuration"
l1_sections: ["Launching Claude Code", "Waybar Controls", "Custom Commands", "MCP Server Tools", "Virtual Monitor", "Knowledge Base", "Configuration"]
tags: [claude, claude-code, mcp, commands, tools, coding, development]
---
# Claude Code in Costa OS

## Launching Claude Code

```sh
# From terminal
claude

# From waybar
# Left-click the 󰚩 icon
```

## Waybar Controls

| Action | What It Does |
|--------|-------------|
| Left-click 󰚩 | Launch Claude Code |
| Right-click 󰚩 | Model picker (switch between Sonnet/Opus) |
| Scroll on 󰚩 | Cycle through project contexts |
| Middle-click 󰚩 | Dangerous mode (skips permission prompts — use carefully) |

## Custom Commands

Type these inside a Claude Code session:

| Command | What It Does |
|---------|-------------|
| `/check-system` | Audit system health, services, disk, memory |
| `/configure-waybar` | Modify waybar config with guidance |
| `/install` | Install and configure a package properly |
| `/theme` | Apply or modify Costa theme elements |
| `/troubleshoot` | Diagnose and fix system issues |

## MCP Server Tools

Costa OS provides an MCP server (`costa-system`) with 30+ tools that let Claude Code interact with the system:

- **System info** — read running processes, services, hardware status
- **Window management** — list, focus, move, resize windows via Hyprland
- **Navigation** — open browsers, navigate URLs, read page content
- **Media control** — play/pause, volume, track switching
- **Screenshots** — capture windows or regions
- **File operations** — read/write/search files

Claude Code uses these tools automatically when relevant to your request.

## Virtual Monitor

Claude Code has its own virtual monitor for visual/interactive work:

- **Monitor**: HEADLESS-2 (1920x1080 @ scale 2)
- **Workspace**: 7
- Claude can open browsers, view pages, and interact with GUIs on this monitor
- Switch to workspace 7 (`SUPER+7`) to see what Claude is doing

## Knowledge Base

21 knowledge files are injected as MCP resources, giving Claude Code deep knowledge about:
- System configuration (Hyprland, Waybar, PipeWire, etc.)
- Costa OS features (voice, AI routing, workflows, etc.)
- Admin tasks (Arch Linux, networking, security, etc.)

Files live in `~/projects/costa-os/knowledge/`.

## Configuration

```sh
# MCP server config (tools, resources)
~/.claude.json

# Custom slash commands
~/.claude/commands/

# Project-specific settings
<project-dir>/.claude.json    # needs hasTrustDialogAccepted: true for -p mode
```
