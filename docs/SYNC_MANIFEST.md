# Costa OS — Documentation Sync Manifest

When a feature is added, changed, or removed, **all files that reference it must be updated**.
This manifest maps every code component to every file that documents or ships knowledge about it.

## Code → Documentation Map

### AI Router (`ai-router/router.py`)
- `knowledge/ai-router.md` — query flow, routing patterns, VRAM tiers, CLI flags
- `knowledge/costa-os.md` — architecture overview, key commands
- `configs/claude/CLAUDE.md` — knowledge file table
- `docs/advertising.md` — smart model routing, context gathering, command safety, escalation

### Context Gathering (`ai-router/context.py`)
- `knowledge/ai-router.md` — context injection section
- `docs/advertising.md` — context gathering bullet list

### Smart Commands (`ai-router/smart_commands.py`)
- `docs/advertising.md` — smart command suggestions section

### Clipboard Daemon (`ai-router/clipboard_daemon.py`)
- `knowledge/costa-os.md` — clipboard intelligence mention
- `docs/advertising.md` — clipboard intelligence section

### Project Switching (`ai-router/project_switch.py`)
- `docs/advertising.md` — project management section

### Navigation (`ai-router/nav.py`)
- `knowledge/costa-nav.md` — full architecture, levels, plans, best practices
- `docs/advertising.md` — costa-nav section (flagship feature)
- `docs/hardware-compatibility.md` — AT-SPI requirements

### Keybinds GUI (`ai-router/keybinds_gui.py`)
- `knowledge/keybinds.md` — GUI docs, bind types, mouse detection
- `docs/advertising.md` — keybinds GUI section

### Keybinds CLI (`ai-router/keybinds.py`)
- `knowledge/keybinds.md` — CLI commands

### Screenshot AI (`ai-router/screenshot_action.py`)
- `docs/advertising.md` — screenshot AI section

### File Search (`ai-router/file_search.py`)
- `knowledge/costa-os.md` — key commands
- `docs/advertising.md` — window management / smart file search

### Window Manager (`ai-router/window_manager.py`)
- `knowledge/hyprland.md` — hyprctl commands
- `docs/advertising.md` — window management section

### Voice Assistant (`voice-assistant/`)
- `knowledge/voice-assistant.md` — full pipeline, keybinds, troubleshooting
- `docs/advertising.md` — voice assistant section
- `docs/system-requirements.md` — audio requirements, AI tier gating

### VRAM Manager (`scripts/ollama-manager.sh`)
- `knowledge/ai-router.md` — VRAM tiers
- `docs/advertising.md` — VRAM manager section
- `docs/system-requirements.md` — GPU tiers and model mapping

### Headless Preview (`scripts/headless-preview.py`)
- `knowledge/customization.md` — headless monitor preview section
- `knowledge/costa-nav.md` — dedicated monitor section
- `docs/advertising.md` — waybar modules table, Claude Code section

### Waybar Templates (`configs/waybar/templates/`)
- `knowledge/customization.md` — template list, placeholder docs
- `docs/advertising.md` — waybar modules table, template system section
- `docs/hardware-compatibility.md` — bar assignment table

### Waybar Generator (`scripts/generate-waybar-config.sh`)
- `knowledge/customization.md` — template regeneration
- `docs/hardware-compatibility.md` — monitor detection logic

### Music Widget (`configs/music-widget/widget.py`)
- `docs/advertising.md` — music widget section

### GUI Installer (`installer/costa_installer.py`)
- `docs/advertising.md` — GUI installer section
- `knowledge/costa-setup.md` — installer description, partition modes
- `iso/airootfs/usr/local/bin/costa-install` — backend `--gui` mode
- `iso/airootfs/usr/local/bin/costa-install-gui` — launcher script
- `iso/airootfs/root/.config/hypr/hyprland.conf` — exec-once target

### Settings Hub (`installer/settings.py`)
- `docs/advertising.md` — settings hub section

### First-Boot (`installer/first-boot.sh`)
- `knowledge/costa-setup.md` — re-running setup, config locations
- `docs/advertising.md` — first-boot wizard section
- `docs/system-requirements.md` — GPU driver install, voice deps

### Installer Wizard (`installer/wizard.py`)
- `knowledge/costa-setup.md` — config.json fields
- `docs/advertising.md` — first-boot wizard section

### Config Schema (`installer/config_schema.py`)
- `knowledge/ai-router.md` — model tiers per VRAM
- `docs/system-requirements.md` — hardware tiers

### MCP Server (`mcp-server/costa_system.py`)
- `knowledge/costa-nav.md` — AT-SPI architecture
- `docs/advertising.md` — Claude Code as native citizen section
- `configs/claude/CLAUDE.md` — MCP resource URIs in knowledge table

### SQLite Persistence (`ai-router/db.py`)
- `knowledge/ai-router.md` — query logging, usage stats, cost tracking, conversation history
- `docs/advertising.md` — usage analytics, budget tracking

### Claude Tool Use (`ai-router/tools.py`)
- `knowledge/ai-router.md` — structured tool use section
- `docs/advertising.md` — tool use section

### Workflow Engine (`ai-router/workflow.py`, `costa-flow` CLI)
- `knowledge/ai-router.md` — workflow engine section
- `docs/advertising.md` — workflow automation section

### ML Router (`ai-router/ml_router.py`)
- `knowledge/ai-router.md` — ML router training section
- `docs/advertising.md` — ML-based routing

### Document RAG (`ai-router/rag.py`)
- `knowledge/ai-router.md` — RAG / document indexing section
- `docs/advertising.md` — document search section

### Request Queue (`ai-router/queue.py`)
- `knowledge/ai-router.md` — request queue section
- `docs/advertising.md` — queue daemon

### Waybar AI Widget (`configs/waybar/templates/main-bar.jsonc`)
- `knowledge/customization.md` — costa-ai module (replaces voice-claude)
- `docs/advertising.md` — waybar modules table (costa-ai replaces voice-claude)

### Knowledge Loader (`ai-router/knowledge.py`)
- `knowledge/ai-router.md` — knowledge system section, tiered loading docs
- `docs/advertising.md` — AI routing / knowledge tiering section

### Tiered System Prompts (`configs/costa/system-prompts/`)
- `knowledge/ai-router.md` — system prompts section
- `docs/advertising.md` — model tier details

### Report to Claude (`ai-router/report.py`)
- `knowledge/ai-router.md` — report to Claude section
- `docs/advertising.md` — self-improving knowledge section
- `configs/waybar/templates/main-bar.jsonc` — ai-report module

### Claude Code Commands (`configs/claude/commands/`)
- `configs/claude/CLAUDE.md` — custom commands section
- `docs/advertising.md` — Claude Code integration section

### Claude Code Setup (`scripts/setup-claude-code.sh`)
- `knowledge/costa-setup.md` — setup process
- `docs/advertising.md` — Claude Code section

### Face Auth / Touchscreen (`installer/first-boot.sh` detect + setup functions)
- `knowledge/security.md` — howdy commands, PAM config, touchscreen setup, troubleshooting
- `knowledge/costa-os.md` — security section overview
- `knowledge/costa-setup.md` — config locations (howdy, touch.conf)
- `knowledge/hyprland.md` — touchscreen & touch gestures section
- `configs/claude/CLAUDE.md` — knowledge file table (security.md entry)
- `docs/advertising.md` — face auth section, touchscreen section, settings hub, first-boot wizard
- `docs/system-requirements.md` — optional hardware, optional software deps
- `docs/hardware-compatibility.md` — laptop support (IR camera, touchscreen)

### Hyprland Config (`configs/hypr/hyprland.conf`)
- `knowledge/costa-os.md` — default keybinds, window rules
- `knowledge/hyprland.md` — config syntax examples
- `knowledge/keybinds.md` — bind list
- `docs/hardware-compatibility.md` — laptop support (touchpad, gestures, lid)

### Packages (`packages/*.txt`, `iso/packages.x86_64`)
- `docs/system-requirements.md` — software dependencies
- `knowledge/costa-setup.md` — if new config domains are added

### Knowledge Files (`knowledge/*.md`)
- `configs/claude/CLAUDE.md` — knowledge file table with MCP resource URIs
- `ai-router/knowledge.py` — `TOPIC_PATTERNS` dict (if topic patterns change)
- All files need YAML frontmatter (l0, l1_sections, tags) — auto-discovered by knowledge.py

### Costa Theme
- `knowledge/costa-setup.md` — color hex values
- `knowledge/customization.md` — theme palette section
- `docs/advertising.md` — desktop & theme section

## Adding a New Feature Checklist

1. Write the code
2. If it adds a new knowledge domain: create `knowledge/<topic>.md`
3. If new knowledge file: add to `configs/claude/CLAUDE.md` table + `ai-router/router.py` KNOWLEDGE_TOPICS
4. Update `docs/advertising.md` with user-facing description
5. If hardware-dependent: update `docs/system-requirements.md` and `docs/hardware-compatibility.md`
6. If new package dependency: add to `packages/base.txt` and/or `iso/packages.x86_64`
7. If new keybind: update `knowledge/keybinds.md` and `knowledge/costa-os.md`
8. If new config location: update `knowledge/costa-setup.md`
9. If new Waybar module: update `knowledge/customization.md` and `docs/advertising.md` module table

## Removing a Feature Checklist

1. Remove the code
2. Remove from all files listed in the map above
3. If knowledge file removed: remove from `configs/claude/CLAUDE.md` table + `ai-router/router.py`
4. Remove package dependencies if no longer needed
