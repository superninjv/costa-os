# Costa OS

AI-native Linux distribution built on Arch Linux + Hyprland. The AI is the OS interface.

## Build & Test
```bash
# Build ISO (requires archiso)
sudo ./scripts/build-iso.sh

# Test in VM
./scripts/test-vm.sh

# Run installer wizard standalone (for development)
python3 installer/wizard.py
```

## Project Structure (public repo)
- `ai-router/` — Core intelligence layer (context gathering, model routing, auto-escalation)
- `packages/` — Package lists by category (base, dev, creative, gaming)
- `configs/` — Default config templates (Costa theme applied)
- `voice-assistant/` — PTT voice assistant source (future: standalone app)
- `scripts/` — Automation and utility scripts
- `branding/` — Logo, wallpapers, boot splash
- `docs/` — User guide, architecture docs
- `knowledge/` — Knowledge base files (shipped with OS, injected into local LLM)
- `mcp-server/` — Claude Code MCP server (system tools, screen reading)

### Private (not in public repo)
- `installer/` — First-run setup wizard (Python/GTK4)
- `iso/` — archiso profile and ISO build scripts

## AI Router
```bash
# Query from CLI (any input modality feeds into this)
costa-ai "what packages do I have for python"
costa-ai --json "is docker running"   # includes metadata (model used, escalation, timing)

# Skip context gathering or escalation
costa-ai --no-context "what is 2+2"
costa-ai --no-escalate "what GPU do I have"
```
The router: gathers live system context → queries local Ollama → detects "I don't know" → escalates to Claude API.

## Architecture
- Base: Arch Linux (archiso)
- Compositor: Hyprland
- Theme: Costa (Mediterranean coastal palette)
- AI Layer: Whisper STT + Ollama (local) + Claude API (cloud) + smart routing
- Package manager: pacman + yay (AUR)

## Workflow Commands
- `/commit` — analyze changes and commit with auto-generated message
- `/deploy` — test, commit, push, invoke deployer agent, healthcheck
- `/ship-site` — push synoros-platform, deploy via deployer agent
- `/sync-docs` — verify all docs match code per SYNC_MANIFEST
- `/feature-dev` — 7-phase structured development workflow
- `/code-review` — parallel agent code review
- `/note` — write to Obsidian vault (`~/notes/`) with frontmatter
- `/workflow` — design n8n automation workflows

## MCP Servers
- **obsidian** — read/write Obsidian vault at `~/notes/` for persistent knowledge
- **n8n** — workflow design knowledge (docs-only, no running instance needed)
- **costa-system** — system tools, screen reading, navigation

## System Agents — USE THESE

**Read `configs/costa/agents/*.yaml` before doing server ops, deploys, builds, or code reviews.** 6 agents (deployer, sysadmin, architect, builder, janitor, monitor) handle these tasks. Invoke via `costa-agents run <name> "instruction"` or the MCP `system_command` tool.

- **After modifying site files** → git push, then deploy via the **deployer** agent
- **After modifying ISO-related files** → use the **builder** agent
- **Server SSH/ops** → use **sysadmin** or **deployer** (they share a serial queue)
- If `costa-agents` CLI isn't available, read the agent YAML for the SSH command and run it directly

## Documentation Sync — MANDATORY

When you add, change, or remove any feature, you MUST update all files that reference it.

**Read `docs/SYNC_MANIFEST.md`** — it maps every code component to every file that documents it.

Three layers must stay in sync:
1. **Knowledge files** (`knowledge/*.md`) — shipped to users, injected into local LLM at runtime via `ai-router/router.py`
2. **Shipped docs** (`docs/*.md`, `configs/claude/CLAUDE.md`) — user-facing documentation and Claude Code guide
3. **Codebase docs** (this file, comments) — developer reference

### Quick rules:
- New feature → update `docs/advertising.md` + relevant `knowledge/*.md` files
- New knowledge file → add to `configs/claude/CLAUDE.md` table + `ai-router/router.py` KNOWLEDGE_TOPICS
- New keybind → update `knowledge/keybinds.md` + `knowledge/costa-os.md`
- New package dep → add to `packages/base.txt` and/or `iso/packages.x86_64`
- New config location → update `knowledge/costa-setup.md`
- New Waybar module → update `knowledge/customization.md` + `docs/advertising.md` module table
- Hardware-dependent feature → update `docs/system-requirements.md` + `docs/hardware-compatibility.md`
- Removed feature → remove from ALL referencing files (check manifest)

### Why this matters:
- `knowledge/*.md` files are the local LLM's brain — stale knowledge = wrong answers to users
- `docs/advertising.md` is the pitch doc — missing features = underselling the product
- `configs/claude/CLAUDE.md` ships to every user's machine — Claude Code reads it on every session
