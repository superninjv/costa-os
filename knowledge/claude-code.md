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
- **Navigation** — open browsers, navigate URLs, read page content via AT-SPI + CLI-Anything
- **Media control** — play/pause, volume, track switching
- **Screenshots** — capture windows or regions
- **File operations** — read/write/search files
- **Vault search** — FTS5 semantic search across Obsidian vault and indexed documents
- **CLI registry** — manage deterministic app wrappers for fast navigation

Claude Code uses these tools automatically when relevant to your request.

## Memory Hooks

Claude Code has two automatic hooks installed:
- **SessionStart** — loads today's + yesterday's daily notes and recent feedback at session start
- **PreCompact** — before context compaction, reminds Claude to save session progress to daily notes

These ensure Claude maintains context across conversations and never loses important information during long sessions.

## Virtual Monitor

Claude Code has its own virtual monitor for visual/interactive work:

- **Monitor**: HEADLESS-2 (1920x1080 @ scale 2)
- **Workspace**: 7
- Claude can open browsers, view pages, and interact with GUIs on this monitor
- Switch to workspace 7 (`SUPER+7`) to see what Claude is doing

## Obsidian Vault — Persistent Memory

Claude Code has read/write access to the Obsidian vault at `~/notes/` via the `obsidian` MCP server. This is Claude's long-term memory — preferences, project context, references, and behavioral corrections persist across conversations.

Vault folders: `projects/`, `feedback/`, `reference/`, `daily/`, `costa-os/`, `architecture/`

Claude should check the vault at conversation start for relevant context, and write notes when learning user preferences, project details, or useful references. Users can browse and edit notes in Obsidian or any text editor.

## Knowledge Base

21 knowledge files are injected as MCP resources, giving Claude Code deep knowledge about:
- System configuration (Hyprland, Waybar, PipeWire, etc.)
- Costa OS features (voice, AI routing, workflows, etc.)
- Admin tasks (Arch Linux, networking, security, etc.)

Files live in `~/.config/costa/knowledge/` (copied from shipped files during first-boot).

## Configuration

```sh
# MCP server config (tools, resources)
~/.claude.json

# Custom slash commands
~/.claude/commands/

# Project-specific settings
<project-dir>/.claude.json    # needs hasTrustDialogAccepted: true for -p mode
```
