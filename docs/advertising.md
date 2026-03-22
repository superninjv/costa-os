# Costa OS — Feature Overview & Advertising Reference

_Private document — does not ship with the OS._

---

## Elevator Pitch

Costa OS is **the easiest Linux distribution ever made.** If something isn't working, ask Claude Code to fix it. If you can't find something, ask Claude Code where it is. Want a new app? "Install Blender." Want your OS to look different? "Make my terminal blue." Want a new keybind? "Bind SUPER+G to open GIMP." Claude Code has full system access, knows every config file, and can change anything in one prompt.

Under the hood, it's an AI-native distribution built on Arch Linux + Hyprland where **the AI is the operating system interface**. Voice, typing, and gestures feed into an intelligent routing layer that uses local models (3B, 7B, 14B, or 32B depending on your GPU) for speed and privacy, automatically escalating to Claude when it needs more power. The user never thinks about which model to use — the system just works.

Every component — from the window manager to the clipboard to the music player — is wired into the AI layer. Claude Code runs as a first-class citizen with its own virtual monitor, system-level MCP tools, and a dedicated shell bar launcher. The result is a desktop where you talk to your computer and it actually understands your system. No typical Linux setup is required — the ISO handles everything, and if you ever want to change something afterward, you just ask.

---

## The Most Powerful Development Platform in the World

Every other OS treats the developer as a human operating a machine. Costa OS treats the developer as a human directing an intelligence.

**Your entire system is programmable in English.** "Set up a Rust project with PostgreSQL, Redis, and a Docker Compose stack" — and it happens. Not a template. Not a wizard. Claude Code reads your actual hardware, your installed packages, your running services, and builds exactly what fits your machine. It writes the configs, installs the dependencies, starts the services, and opens your editor to the right file.

**The AI knows your system better than you do.** Every query gets injected with live context — running processes, GPU utilization, disk space, network state, Docker containers, git repos, PipeWire audio routing, Hyprland window layout. When you ask "why is my build slow," it doesn't guess. It checks your CPU load, your swap usage, your running containers, and your compiler flags. Then it fixes it.

**Local models for speed. Cloud models for power. You never choose.** The VRAM manager keeps the largest model your GPU can fit resident in memory. Simple questions get answered in under a second without touching the internet. Complex questions auto-escalate to Claude with 30+ structured tools — system queries, safe actions, and ask-first operations all executed via the Anthropic tool_use API. Launch a game and VRAM gets tight? Models step down silently. Close the game? They reload in seconds. The routing layer handles 15+ categories of queries — system administration, code generation, file search, window management, project switching, screenshot analysis, navigation — each dispatched to the optimal model and tool chain. An ML classifier trained from your actual usage data continuously improves routing accuracy.

**Your AI has its own workspace.** Claude Code operates on an invisible virtual monitor — opening browsers, reading documentation, filling forms, running research — without ever interrupting your screen. It reads applications through the accessibility tree at 112x fewer tokens than screenshots. A 10-step automation task that costs $1.38 with screenshot-based agents costs $0.01 here.

**Voice, text, keyboard, mouse — every input modality feeds the same brain.** Push-to-talk transcribes in 500ms via GPU-accelerated Whisper. The clipboard auto-classifies what you copy and offers contextual actions. Screenshots get instant AI analysis and OCR. Keybinds, shell bar modules, rofi menus, and the settings hub are all entry points into the same intelligence layer.

**Development tools are first-class, not afterthoughts.** pyenv, nvm, SDKMAN, Rust toolchain, Docker, k8s, lazygit, zellij — pre-configured and ready. Claude Code ships with custom commands for review, test, refactor, explain, and debug. MCP servers give it direct access to your databases and filesystems. Git is configured with delta for beautiful diffs. Every language server, every linter, every formatter — ask for it and it's installed and configured in seconds.

**The result:** a development environment where the distance between intent and execution is one sentence. No context switching. No documentation hunting. No config file archaeology. You describe what you want, and the most capable AI system ever built — with full knowledge of your exact hardware, your exact software, and your exact workflow — makes it happen.

---

## The AI Navigation System (costa-nav)

### The Problem

Traditional computer use for AI agents requires screenshots — each one costs **~9,180 tokens** of vision processing. A single multi-step task can burn through dollars of API credits just looking at the screen.

### The Solution

costa-nav reads applications through deterministic CLI wrappers (~50ms, zero tokens) or the Linux accessibility tree (AT-SPI) with local Ollama interpretation. Claude never sees raw page content — it gets compact JSON answers.

### The Numbers

| Method                           | Tokens Claude reads | Relative cost |
| -------------------------------- | ------------------- | ------------- |
| Screenshot (industry standard)   | ~9,180              | 112x          |
| Raw page text                    | ~929                | 11x           |
| **costa-nav query**              | **~82**             | **1x**        |
| **costa-nav plan (conditional)** | **~51**             | **0.6x**      |
| **CLI-Anything fast path**       | **~30**             | **0x (deterministic)** |

**112x fewer tokens than screenshots.** For a task requiring 10 screen reads: **$1.38 → $0.01**. With CLI-Anything wrappers, many reads drop to ~50ms with zero LLM tokens.

### Speed Tiers

- **CLI-Anything tier** (~50ms) — Deterministic app queries through CLI wrappers. "What tabs are open?" routes to `cli-anything-firefox tabs list --json`. Zero LLM tokens, zero model calls. Ships with 12 app wrappers (Firefox, Thunar, VS Code, GIMP, OBS, and more).
- **Regex tier** (<50ms) — Simple value reads (window title, focused element) extracted with pattern matching. No model call.
- **Fast tier** (~3s) — Batch Ollama queries for structured data extraction. Multiple questions answered in one model call.
- **Smart tier** (~13s) — Conditional multi-step plans. Read → decide → act → verify, all executed locally in a single round trip.

### How It Works

1. Claude sends a plan: "check credit balance, if under $10 find the warning message"
2. costa-nav checks for a CLI-Anything wrapper first (~50ms, deterministic)
3. If no wrapper: reads the app via AT-SPI, local Ollama interprets (free, ~3s)
4. Actions execute mechanically (clicks, typing, scrolling)
5. Claude gets back 30-80 tokens of structured answers

**One round trip. Zero screenshots. Zero API cost for screen reading.**

### The Virtual Monitor

Claude operates on an **invisible headless display** — a virtual monitor that takes zero physical screen space. It can open its own browser, navigate pages, fill forms, and research — all without touching the user's screen. The user never sees interruptions.

### Self-Learning

The system learns as it runs:

- **Site knowledge** auto-accumulates: element locations, page behavior, what worked (`~/.config/costa/nav-sites/`)
- **Saved routines** let Claude trigger complex multi-step plans with one word (`~/.config/costa/nav-routines/`)
- **Tool knowledge** improves over time as Claude discovers patterns and anti-patterns

---

## Claude Code as Native Citizen

Costa OS treats Claude Code as the **ultimate customization engine** — not a bolted-on tool, but a core OS component that can modify ANY config, install ANY package, change ANY theme, and create ANY script. Works with Claude Pro/Max subscriptions (recommended) or API keys — no separate billing required if you're already on a Claude Plan. It knows the entire system layout: every config file location, every package manager, every service, every keybind. The Settings Hub and Keybinds GUI exist for quick visual changes, but Claude Code handles anything — from "make the bar thicker" to "set up a full Rust development environment" to "configure PipeWire for low-latency audio recording."

This is what makes Costa OS the easiest Linux distro ever: you never need to learn where configs live, what format they use, or how to restart services. Just describe what you want.

- **Full System Access** — Claude Code can edit Hyprland configs, install packages via pacman/yay, modify AGS shell modules, change themes, create systemd services, write scripts, configure development environments — anything you can do in a terminal, described in plain English
- **MCP Server** — Gives Claude system eyes and hands via AT-SPI screen reading, typing, clicking, scrolling, window management, and system commands
- **Virtual Headless Monitor** — Invisible display (zero screen space) where Claude can open browsers, navigate pages, and research independently. Live preview available via shell bar 󰍹 icon (click to toggle a floating window showing what Claude sees)
- **CLAUDE.md Template** — First-boot generates a hardware-aware CLAUDE.md with detected GPU, monitors, audio devices, installed packages, and project paths. Claude Code reads this on every session, so it always knows your exact hardware and setup
- **Shell Bar Launcher** — Dedicated module with multi-action support:
  - Left click: launch Claude Code
  - Middle click: dangerous mode (auto-approve)
  - Right click: model picker
  - Scroll: cycle projects
- **Usage Tracking** — Shell bar module showing Claude usage (Plan quota or API spend and token counts)
- **Knowledge Bases as MCP Resources** — 21 topic-specific knowledge files available as MCP resources (`costa://knowledge/<topic>`). Claude Code reads them on demand when relevant — audio questions pull pipewire-audio.md, package questions pull arch-admin.md, etc.
- **Obsidian Vault as Persistent Memory** — Every Costa OS install includes an Obsidian vault at `~/notes/` connected to Claude via MCP. Claude reads and writes notes to remember your preferences, track project context, store references, and maintain behavioral corrections across conversations. The vault is organized by purpose: `projects/`, `feedback/`, `reference/`, `daily/`, `architecture/`. You can browse and edit notes in Obsidian or any editor — Claude keeps them up to date automatically.
- **Daily Session Notes** — Each Claude Code session auto-creates a daily note (`~/notes/daily/YYYY-MM-DD.md`). Claude appends session progress, decisions, and discoveries throughout the day. Today's and yesterday's notes load at session start, giving Claude continuous context across conversations.
- **Memory Flush Before Compaction** — When Claude Code's context window fills up and compacts, a hook automatically triggers Claude to save important session context to daily notes before it's lost. No more "I don't have context about what we were doing" after long sessions.
- **Vault Search (FTS5)** — Full-text search across all notes and indexed documents via the `vault_search` MCP tool. BM25-ranked results with file paths and relevance scores. The vault is auto-indexed hourly via a systemd timer.
- **Multi-Channel Presence** — Costa AI is accessible from Telegram (`/ai <query>`) and Discord, not just the terminal. Same AI, same memory, same knowledge base — different interface. Configure API tokens in `~/.config/costa/env`.
- **Custom Slash Commands** — Pre-built commands for common tasks: `/check-system` (health check), `/install <pkg>` (smart install with AUR fallback), `/theme` (modify Costa palette), `/configure-shell` (add/edit modules), `/troubleshoot` (diagnose issues)
- **Auto-Configuration** — First boot generates hardware-aware CLAUDE.md, configures MCP server, Obsidian vault, memory hooks, and RAG indexing. Re-run anytime via `costa-settings`

---

## AI Intelligence Layer

### Smart Model Routing

Every query is analyzed and routed to the optimal model automatically. The VRAM manager selects the best local model your GPU can fit — 3B, 7B, 14B, or 32B — see [GPU Capability Tiers](#gpu-capability-tiers) below.

| Route        | Model                              | Use Case                                     | Latency |
| ------------ | ---------------------------------- | -------------------------------------------- | ------- |
| Local        | 7B / 14B / 32B (best for your GPU) | General knowledge, system help, reasoning   | ~1-3s   |
| Local (fast) | 3B                                 | Summaries, quick classification              | ~0.3s   |
| Local + web  | Ollama + wttr.in                   | Weather (fetches data, reasons locally)      | ~2s     |
| Cloud (fast) | Claude Haiku + WebSearch           | Live news, scores, trending                  | ~2-4s   |
| Cloud (code) | Claude Sonnet                      | Code generation, debugging, multi-file edits | ~3-5s   |
| Cloud (deep) | Claude Opus                        | Deep research, architecture, security audit  | ~5-10s  |

### Zero-Touch Escalation

If the local model says "I don't know," it silently escalates to Claude. Detection uses 15+ regex patterns matching hedge phrases, capability disclaimers, and deferral language. The user never manages model selection.

### Context Gathering

Every AI query gets injected with **real system state** based on topic detection:

- **Package info** — `pacman -Q` queries for installed/available packages
- **Service status** — `systemctl` for running/failed services
- **Processes** — `top`/`procs` for resource usage
- **GPU/VRAM** — Real-time utilization and memory pressure
- **Disk space** — Mount points and usage
- **Network** — `ip`/`ss` for connections and interfaces
- **Audio** — `wpctl` for sink/source configuration
- **Hyprland state** — Active windows, monitors, workspaces, keybinds via `hyprctl`
- **Docker** — Running containers, images, compose projects
- **Git** — Repository status across `~/projects/`
- **System logs** — `journalctl`/`dmesg` for recent errors

The AI doesn't guess about your system — it knows.

### Command Safety

Three tiers of command execution:

- **Whitelist (auto-execute)** — `wpctl`, `hyprctl`, `playerctl`, `brightnessctl`, `systemctl status`, `pacman -Q`
- **Blacklist (never without warning)** — `rm -rf`, `dd`, `mkfs`, `shutdown`
- **Ask tier** — Everything else requires confirmation

### Tiered Knowledge System

21 knowledge files with YAML frontmatter for intelligent loading:
- **Auto-discovery** — Drop a new `.md` file in `~/.config/costa/knowledge/`, it's immediately available. No code changes needed.
- **Tiered loading** — 3B models get ~800 tokens of knowledge (summaries only). 7B gets ~1,500 (key sections). 14B gets ~3,000 (full content for top matches). Knowledge is matched by regex patterns + semantic tags.
- **Tiered system prompts** — The system prompt itself scales with model size. 3B gets 20 lines of essential rules. 14B gets the full ~80-line prompt with hardware details, keybinds, and 5 few-shot examples.
- **XML-structured prompts** — `<context>`, `<knowledge>`, `<query>` delimiters with query positioned last (highest attention for Qwen models).
- **Temperature tuning** — 0.1 for action commands (precision), 0.3 for general knowledge, 0.5 for conversational followups.

### Self-Improving Knowledge (Report to Claude)

When the local model gives a wrong answer, click the 󰚑 button in the shell bar. This triggers an automated feedback loop:
1. The failed query + response is sent to Claude Haiku
2. Claude identifies what went wrong — missing knowledge, wrong file matched, or hallucination
3. Claude generates a JSON patch for the relevant knowledge file
4. The patch is applied to `~/.config/costa/knowledge/` automatically
5. The corrected answer is shown via notification
6. Next time someone asks the same question, the local model gets the corrected knowledge

Corrections are logged in `.corrections.json` for review. The local LLM literally gets smarter over time based on user feedback, without retraining.

### Rolling Conversation

Conversation history stored in SQLite (`~/.config/costa/costa.db`) for persistent multi-turn dialogue across voice and text inputs. Context persists between input modalities and across reboots — start a question by voice, follow up by typing, review it tomorrow.

### SQLite Persistence & Usage Analytics

Every query is logged to a local SQLite database with model used, latency, token counts, and cost estimates:

- `costa-ai --history` — browse past queries and responses
- `costa-ai --search "docker"` — full-text search across query history
- `costa-ai --usage` — usage statistics by model, time period, and cost
- `costa-ai --budget 5.00` — set daily/monthly spending limits with automatic cloud query blocking

### Cancel Mechanism

Long-running queries can be cancelled instantly:

- `costa-ai --stop` — sends SIGTERM to the running costa-ai process via PID file (`/tmp/costa-ai.pid`)
- Shell bar stop button — click the stop icon on the costa-ai widget during processing
- Clean teardown — model inference and API calls are interrupted gracefully

### Claude Tool Use (30+ Structured Tools)

When queries escalate to Claude, the router provides 30+ structured tools via the Anthropic tool_use API:

- **System queries** — read processes, services, packages, disk, network, GPU, audio state
- **Safe actions** — adjust volume, switch workspace, control media, toggle settings
- **Ask-first actions** — install packages, restart services, modify configs (requires confirmation)

Claude doesn't just answer — it acts. "Turn up the volume and skip this track" executes both actions in one round trip.

### Workflow Engine (costa-flow)

n8n-style YAML workflow automation in `~/.config/costa/workflows/`:

- `costa-flow run morning-briefing` — execute a workflow
- `costa-flow list` — see all available workflows
- `costa-flow enable system-health` — activate a workflow on its systemd timer schedule
- 10 built-in templates: morning-briefing, system-health, backup-check, smart-update, docker-watch, log-digest, project-standup, security-scan, cleanup, ollama-model-update
- Write your own: YAML files with steps, conditions, schedules, and AI-powered decision nodes

### ML-Trained Query Router

A PyTorch MLP classifier learns from your usage patterns to improve routing accuracy:

- `costa-ai --train-router` — retrain from logged query data
- Automatically categorizes queries into local/cloud/code/research tiers
- Gets smarter over time — the more you use costa-ai, the better routing gets

### Document RAG (Retrieval-Augmented Generation)

Index your own documents for AI-powered search:

- `costa-ai --index ~/projects/myapp/docs` — index a directory
- `costa-ai --index ~/notes` — add personal notes to the search corpus
- FTS5-based full-text search with relevance ranking
- Indexed content is injected as context when relevant to your queries

### Request Queue

A Unix socket priority queue daemon handles concurrent requests:

- Voice queries get highest priority (immediate response)
- Background workflows queue behind interactive queries
- Prevents model contention when multiple sources query simultaneously

### Presets

- `costa-ai --preset code` — switch to code-optimized routing (prefer Sonnet)
- `costa-ai --preset research` — deep research mode (prefer Opus)
- `costa-ai --preset fast` — speed-first (prefer local, minimal context)

---

## Voice Assistant

- **Push-to-Talk** — SUPER+ALT+V speaks to AI (Claude mode), SUPER+ALT+B types transcription into focused window
- **0.5s Transcription** — Whisper tiny.en with Vulkan GPU acceleration
- **DeepFilterNet + Silero VAD** — Noise floor crushed from 0.2 to 0.004 RMS, automatic speech-end detection. Works in noisy rooms
- **Auto-Submit** — Just talk and release. Say "draft" or "hold" to prevent submission
- **Shell Bar Integration** — Spinner while processing, scrolling response text, click for full details
- **Text Input Fallback** — Click the shell bar voice icon for rofi text input, right-click to view last output

---

## VRAM Manager

- **Automatic Model Balancing** — Monitors GPU memory pressure and hot-swaps between model tiers based on what other apps need VRAM. The manager dynamically selects the largest model your GPU can fit right now:

| Available VRAM | Smart Model (resident) | Fast Model | What You Get |
|---------------|----------------------|------------|-------------|
| **12GB+** | qwen2.5:14b (~11GB) | qwen2.5:3b | Best local intelligence — handles most queries without cloud |
| **8-12GB** | qwen2.5:7b (~6.5GB) | qwen2.5:3b | Strong local reasoning, occasional cloud escalation |
| **6-8GB** | qwen2.5:7b (~6.5GB) | qwen2.5:3b | Good reasoning, costa-nav works. Tight VRAM — may step down to 3B under GPU pressure |
| **4-6GB** | qwen2.5:3b (~4GB) | qwen2.5:3b | Quick local answers, more cloud escalation. costa-nav works with CLI-Anything wrappers; AT-SPI queries limited at 3B |
| **<4GB / Gaming** | All models unloaded | On-demand | Cloud-only while GPU is busy (games, rendering, etc.) |

- **Budget-Based** — Subtracts other app VRAM usage + 2GB headroom, avoids thrashing
- **Real-Time Adaptation** — Launch a game? Models unload automatically. Close it? Best model reloads within seconds
- **No Configuration** — Users never think about VRAM. The system keeps the best possible model loaded at all times. Voice commands always use the current best available model.

---

## Music Widget

GTK3 floating MPRIS controller, launched by clicking now-playing in the shell bar:

- **Album art** (140px) with progress bar and seek controls
- **Audio quality badge** — Live stream format from PipeWire (e.g. "24bit / 96kHz"), teal highlight for hi-res (>16bit or >48kHz)
- **Player switching** — Seamlessly switch between Spotify, Firefox, VLC, Strawberry, and 10+ other MPRIS players with per-player icons
- **Queue browsing** — View and jump to any track in the current playlist, current track highlighted
- **Library search** — Search Strawberry's SQLite database by title, artist, or album without opening Strawberry
- **Playlist switching** — Switch between playlists via D-Bus without opening Strawberry
- **Cold start** — If no player is running, one button launches Strawberry, starts playback, and hides the window
- **Show/hide toggle** — Toggle Strawberry between visible and hidden (special workspace) from the widget header
- **Repeat modes** — Cycle through None → Playlist → Track repeat
- **Tabbed interface** — Queue / Search / Playlists / Players tabs with smooth crossfade transitions
- **Costa-themed** — Full palette applied (dark base, sea/foam/sand accents), 420x680px floating window

---

## Keybinds GUI

GTK4/libadwaita app for managing all Hyprland keyboard and mouse bindings:

- **Visual keyboard shortcut editor** — Categorized by: Applications, Launchers & Clipboard, Window Management, Workspaces, Monitors, Mouse, Media, Screenshots, Costa AI, Session
- **Keyboard recorder** — Click "Record," press your key combination, binding auto-detected including modifiers
- **Conflict detection** — Real-time checking against active Hyprland binds when recording
- **Mouse button detection** — evdev-based button identification. Press "Start Detection," then press any mouse button to identify its code
- **Per-device button bindings** — Auto-discovers all connected mice via sysfs (no sudo needed), deduplicates wireless receiver + wired connections, configure each independently
- **libratbag integration** — Banner prompts for advanced mouse hardware remapping (DPI shift, etc.)
- **Search and filter** — Instant filter across all keybinds by key, action, or description
- **Bind type support** — `bind`, `binde` (repeat), `bindm` (mouse), `bindl` (locked), `bindr` (release), `bindn` (no consume)

---

## Settings Hub

GTK4/libadwaita central settings panel — a proper `.desktop` app accessible from rofi, the shell bar (⚙ icon), or CLI (`costa-settings`). Built-in AI assistance: if a setting fails to apply or you're confused about an option, the local AI and Claude help troubleshoot right there in the panel.

- **Display** — Monitor detection and layout, shell bar config generation, wallpaper picker (images + video)
- **Security** — Face enrollment and testing (if IR camera detected)
- **Input** — Touchscreen toggle (if detected), launches keybinds GUI
- **AI Assistant** — Ollama model management (list/pull), Claude Plan login (Pro/Max, recommended) or API key entry for advanced users (Anthropic/OpenAI) with secure storage (`chmod 600`), voice assistant status
- **Development** — GitHub CLI authentication, SSH key generation/viewing
- **System** — Costa OS version display with update check, `costa-update` (AI-assisted: pulls Costa layer via git, updates system packages, Claude reviews changes and fixes breakage), chezmoi dotfiles sync, re-run first-boot to regenerate all configs
- **AI Help** — Every section has AI assistance — if something fails or you're unsure what a setting does, ask and get an instant explanation or fix
- **Async status checks** — Every item shows live status (green/yellow/red) loaded in background threads: "Authenticated," "3 models," "Running," etc.

---

## Project Management

Voice-activated project context switching: "costa-ai switch to my-project" and the system does the rest.

- **YAML-based configs** — `~/.config/costa/projects/*.yaml` define project name, directory, workspace, app layout, env vars, setup commands, and keywords
- **Fuzzy matching** — Match by name, partial name, or keywords. "switch to music tabs" finds the right project
- **Full workspace setup** — Switches workspace, launches editor + terminal + browser in configured layout positions, sets environment variables, runs setup commands (e.g., `docker compose up`)
- **Smart positioning** — Apps placed in master/stack layout based on configured positions (left, right, top-right, etc.)
- **Shell bar module** — One-click project switcher with rofi selection

---

## Screenshot AI

Select any screen region and get instant AI analysis:

- **Select & capture** — `slurp` for region selection, `grim` for capture
- **Claude Haiku analysis** — Image sent to Claude Haiku for description, error detection, and OCR
- **Auto-classify** — Detects errors/stack traces and elevates notification urgency
- **OCR extraction** — Readable text extracted and saved separately to `/tmp/costa-screenshot-ocr.txt`
- **Clipboard integration** — Full analysis copied to clipboard automatically
- **Keybind accessible** — Bound to screenshot key, results via dunst notification

---

## Clipboard Intelligence

Watches clipboard via `wl-paste` and auto-classifies content:

- **Content types detected**: error/stack trace, URL, JSON, file path, shell command, code snippet
- **Language detection** for code: Python, JavaScript, Rust, Java, Go, C/C++
- **Contextual notification actions**:
  - Error/stack trace → "Explain with AI"
  - URL → "Open in browser"
  - JSON → "Format/pretty-print"
  - Shell command → "Run in terminal"
  - Code snippet → "Analyze with AI"
- **Debounced** — No duplicate triggers on rapid clipboard changes
- **systemd service** — Runs as `costa-clipboard.service` with resource limits (memory, CPU)

---

## Face Authentication (Howdy)

Windows Hello-style face unlock — detected automatically, enabled if your laptop has an IR camera:

- **IR Camera Auto-Detection** — `v4l2-ctl` scans `/dev/video*` for infrared/Hello capabilities during first-boot
- **PAM Integration** — Face auth for login (greetd), sudo, and screen lock (hyprlock)
- **Password Fallback** — Face is "sufficient", not "required" — password always works
- **Easy Enrollment** — `sudo howdy add` to enroll, `sudo howdy test` to verify
- **Settings Hub** — Enroll/manage faces from Costa OS Settings → Security
- **Hardware-Gated** — Only shown in wizard and settings if IR camera is present

---

## Touchscreen Support

Full touch input for laptops and 2-in-1 devices — detected automatically, enabled if touchscreen hardware is present:

- **Auto-Detection** — `libinput list-devices` identifies touch-capable devices during first-boot
- **On-Screen Keyboard** — squeekboard auto-starts, floats pinned at bottom of screen
- **Multi-Touch Gestures** — hyprgrass plugin for Hyprland:
  - 3-finger swipe up/down → launcher / close window
  - 3-finger swipe left/right → switch workspace
  - 4-finger swipe up/down → fullscreen / toggle floating
  - Long press → move window
- **Dedicated Config** — `~/.config/hypr/touch.conf` auto-generated, sourced from hyprland.conf
- **Hardware-Gated** — Only shown in wizard and settings if touchscreen is present

---

## Smart Command Suggestions

Predicts what you want to type next:

- **Bigram analysis** — Learns from zsh history which commands follow which (e.g., `git add` → `git commit`)
- **Directory-aware** — Different suggestions in different directories based on actual usage
- **Built-in sequences** — Ships with 25+ common workflows (git, cargo, npm, docker, systemctl)
- **File extension context** — Detects project type from files in current directory, suggests relevant build/run commands
- **Error correction** — When a command fails, suggests the fix (missing package, permission issue, typo)

---

## SSH Quick-Connect

Shell bar module for one-click SSH connections:

- **Shell bar integration** — SSH icon in the bar, click to open connection menu
- **Saved hosts** — Pull from `~/.ssh/config` for instant connection

---

## AGS Shell: Hover-Reveal Glassmorphic Desktop Shell

The desktop shell is built from scratch in AGS v3 (Aylur's GTK Shell) using TypeScript/TSX with reactive state management. It is not a stock bar. It is a purpose-built control surface for the entire AI layer, designed to stay out of your way until you need it.

### Hidden by Default

The bar does not sit on screen permanently. A subtle notch trigger (800px wide, 4px tall) sits at the top center of the primary monitor. Hover it, and the full bar slides down with a 300ms animation. Move your cursor away, and it waits 1.2 seconds before retracting, so you can glance at the clock or click a module without the bar snapping shut on you.

### Glassmorphic SCSS Theme

The bar renders with a frosted glass effect: blurred background, subtle transparency, and the full Costa Mediterranean palette as accent colors. Sea blue for active states, foam teal for highlights, terracotta for warnings, sand gold for labels. Dark navy base with warm white text. Every widget follows the same visual language.

### Widgets

| Widget                    | What It Does                                                              |
| ------------------------- | ------------------------------------------------------------------------- |
| **Workspaces**            | Clickable workspace indicators with active/occupied state                 |
| **Git status**            | Branch + dirty state for the current project                              |
| **Now playing**           | Current track + artist, click to open the music widget                    |
| **Audio**                 | Volume slider and output device control                                   |
| **PTT voice status**      | Voice assistant state indicator with processing feedback                  |
| **Clock**                 | Time and date, center-anchored                                            |
| **Power**                 | Session controls (logout, reboot, shutdown)                               |

---

## Monitor-Aware Bar Routing

Each monitor gets a purpose-built bar variant. The shell reads connected monitors from Hyprland and assigns the right layout automatically.

| Monitor Type          | Bar Variant                    | What You See                                                    |
| --------------------- | ------------------------------ | --------------------------------------------------------------- |
| **Primary**           | Notch trigger + full bar       | Hidden by default. Hover the notch to reveal all widgets        |
| **Secondary**         | Minimal pill                   | Compact floating pill showing clock and workspace dot indicators |
| **Portrait**          | Compact performance bar        | Vertical-friendly layout with CPU, GPU, RAM, and temperature    |
| **Headless (Claude)** | Claude workspace bar           | Minimal bar for Claude's virtual monitor                        |

No config generation scripts. No template stitching. The TypeScript source handles monitor detection at runtime via Hyprland IPC events. Plug in a new display and the correct bar appears. Unplug it and the bar is gone.

### macOS-Style Dock

nwg-dock-hyprland provides an auto-hiding application dock at the bottom of the primary monitor. Pin your favorite apps, see running windows, and launch with a click. The dock hides when not in use, matching the bar's stay-out-of-the-way philosophy.

---

## Desktop & Theme

- **Costa Theme** — Custom Mediterranean coastal palette applied consistently across 15+ config domains:
  - Base: `#1b1d2b` (deep navy)
  - Mantle: `#161821`
  - Surface: `#252836`, `#2f3345`
  - Sea: `#5b94a8` (primary accent)
  - Foam: `#7eb5b0`
  - Sand: `#c9a96e`
  - Terracotta: `#c07a56`
  - Olive: `#8b9968`
  - Rose: `#b87272`
  - Text: `#d4cfc4`
- **Everywhere** — Hyprland, AGS shell, GTK (adw-gtk3-dark), Qt (Fusion dark), Ghostty, Rofi, Dunst, music widget, keybinds GUI, settings hub
- **Font** — JetBrains Mono Nerd Font for everything
- **Icons** — Papirus-Dark + Bibata-Modern-Ice cursor
- **Live Wallpaper** — mpvpaper with galaxy video, auto-pauses when windows cover 37.5%+ of the desktop
- **Wallpaper Engine Support** — Optional linux-wallpaperengine integration for Steam Workshop wallpapers (video, 2D scenes). Note: complex 3D scenes may have limited support on some GPUs
- **Multi-Monitor** — Any number of monitors supported, auto-configured at first boot
- **Primary Monitor Pinning** — All notifications, floating panels, settings dialogs, and music widget always appear on the primary monitor regardless of current focus

---

## Window Management

- **Natural language control** — "Put my editor on the left and browser on the right" executes as Hyprland dispatch commands
- **Smart file search** — "Find that Rust file I was editing yesterday with the websocket code" — searches by content, modification time, git history, and frecency
- **Vim-style navigation** — HJKL for window focus, SUPER as mod key
- **Workspace mapping** — Auto-configured per monitor layout (e.g. 1-4 on main, additional workspaces on secondary displays)

---

## GUI Installer

Full GTK4/Libadwaita graphical installer — no CLI required:

1. **Welcome** — Costa branding + get started
2. **Network** — WiFi scan with signal bars, password entry, auto-detect ethernet
3. **Disk Selection** — Visual disk cards (model, size, transport), auto-filters live USB
4. **Partition Strategy** — Three modes:
   - **Erase entire disk** — clean install with red warning banner
   - **Install alongside** — detect existing OS, resize slider for dual-boot
   - **Manual** — pick existing root + EFI partitions
5. **User Setup** — Username (live validation), hostname, password with match indicator
6. **Summary + Confirmation** — Review all choices, destructive action dialog
7. **Installation Progress** — Real-time progress bar + scrollable log
8. **Done** — Reboot button

## First-Boot Wizard

GTK4 setup wizard with full Costa color palette (runs after first reboot):

1. **Hardware auto-detection** — CPU (cores, model), RAM, GPU (vendor, VRAM, max AI tier), monitors (resolution, refresh rate), audio devices (microphones, speakers)
2. **AI tier selection** — Cloud-only → Voice-only → Voice + LLM → Full Workstation, with automatic VRAM-based recommendation and per-tier model pairs
3. **Ollama model configuration** — Smart model + fast model pair recommended per GPU capability
4. **Whisper model + backend** — Model size and acceleration backend (Vulkan/CPU) auto-selected
5. **AI Navigation** — Optional virtual headless monitor for Claude Code
6. **Face Authentication** — If IR camera detected, enable howdy face unlock (login, sudo, lock screen)
7. **Touchscreen** — If touchscreen detected, enable touch input, on-screen keyboard, and gestures
8. **Claude Plan login or API keys** — Sign in with Claude Pro/Max plan (recommended, far cheaper than API for most users) or enter API keys for programmatic access. OpenAI key optional. All stored securely
9. **GitHub authentication** — Optional gh CLI setup
10. **Voice keybinds** — Choose PTT binding (SUPER+ALT+V default, SUPER+ALT+Space, or custom)
11. **Package categories** — Base, developer tools, creative apps, gaming
12. **Audio device selection** — Microphone and speaker from detected devices
13. **Summary + confirm** — Full config review before applying

Then `first-boot.sh` runs: hardware detection, monitor config generation, AGS shell deployment, AI system prompt generation, Claude Code knowledge file installation, nwg-dock setup, and config deployment.

**Time from bare metal to fully AI-native desktop: ~15 minutes.**

---

## Agent Pool

Specialized background agents that handle infrastructure tasks autonomously:

| Agent | Role | Queue |
|-------|------|-------|
| **sysadmin** | Server ops, SSH, service management | remote (serial) |
| **architect** | System design, code review, planning | unlimited |
| **janitor** | Disk cleanup, log rotation, cache clearing | local (serial) |
| **builder** | ISO builds, test suites, compilation | local-heavy (serial) |
| **deployer** | Push code to servers, restart services, healthchecks | remote (serial) |
| **monitor** | Uptime checks, resource alerts, log watching | unlimited |
| **navigator** | Screen reading, app interaction, UI automation (CLI → AT-SPI → nav_plan) | local (2 concurrent) |

Resource queues enforce concurrency — the remote queue ensures only one agent SSHs at a time (multiple sessions crash it). Agents are dispatched via CLI (`costa-agents dispatch sysadmin "restart nginx"`) or by other Claude Code agents.

Each agent has a YAML definition with role description, system prompt, tool access list, and server credentials. Agents run tasks through the AI router and report results via desktop notification.

---

## Technical Architecture

```
User Input (voice / text / gesture / workflow trigger)
       │
       ▼
   Request Queue (Unix socket, priority-based)
       │
       ▼
   costa-ai Router
       │
       ├─ ML Classifier (PyTorch MLP, trained from usage data)
       │   └─ Falls back to regex patterns if untrained
       │
       ├─ Pattern Detection
       │   ├─ Window commands → hyprctl dispatch
       │   ├─ File search → frecency + content search
       │   ├─ Keybind queries → hyprland.conf parser
       │   ├─ Project switch → workspace + env setup
       │   ├─ Screenshot AI → grim + Claude Haiku vision
       │   └─ Navigation → costa-nav (AT-SPI + Ollama)
       │
       ├─ Context Gathering
       │   ├─ Topic detection → select relevant system data
       │   ├─ Package, service, process, GPU, disk, network, audio
       │   ├─ Hyprland state, Docker, git, system logs
       │   ├─ Knowledge base injection (21 topic files)
       │   └─ Document RAG (FTS5 search over indexed dirs)
       │
       ├─ Local Ollama (3B / 7B / 14B / 32B based on VRAM)
       │   ├─ System context injected
       │   ├─ Knowledge base selected
       │   └─ "I don't know" → auto-escalate
       │
       ├─ Claude API (with 30+ structured tools)
       │   ├─ Haiku: live web, quick answers, screenshot analysis
       │   ├─ Sonnet: code generation (tool_use for system actions)
       │   └─ Opus: deep research, architecture
       │
       └─ SQLite Logger (costa.db)
           ├─ Query history, model used, latency, tokens, cost
           ├─ Usage analytics and budget enforcement
           └─ Training data for ML router
```

---

## What Makes Costa OS Different

| Feature           | Traditional Linux                | Costa OS                                                                       |
| ----------------- | -------------------------------- | ------------------------------------------------------------------------------ |
| Find a file       | `find / -name "*.rs"`            | "find that rust file from yesterday"                                           |
| Check system      | Open terminal, run commands      | "is docker running?" → instant answer with live data                           |
| Window layout     | Manual tiling/dragging           | "editor left, browser right"                                                   |
| AI assistant      | Separate app, copy-paste context | AI knows your system state, runs commands directly                             |
| Voice input       | Not built in                     | Push-to-talk with 0.5s transcription                                           |
| Model management  | Manual install, manual selection | Automatic VRAM-aware hot-swapping                                              |
| Screen automation | Screenshots ($1.38/task)         | AT-SPI text reading ($0.01/task)                                               |
| AI workspace      | Shares your screen               | Invisible virtual monitor                                                      |
| Clipboard         | Passive text buffer              | Auto-classifies content, offers contextual AI actions                          |
| Music control     | Open Spotify, find the window    | Click shell bar, search library, switch players/playlists, see live audio quality |
| Keybind config    | Edit hyprland.conf by hand       | Visual GUI with recorder, conflict detection, mouse support                    |
| Settings          | Scattered config files           | Central hub with live status indicators                                        |
| Project context   | cd + manual setup                | "switch to my-project" → workspace, editor, terminal, env vars                 |
| Screenshot        | Save to file                     | Select region → AI analysis + OCR → clipboard                                  |
| Install software  | Search repos, resolve deps, edit configs | "Install Blender and set it up for GPU rendering"                          |
| Customize anything | Edit 15+ config files by hand   | "Add a CPU monitor to the shell bar" or just describe it in plain English      |
| Face unlock       | Separate app, manual config      | Auto-detected IR camera, one toggle in wizard, `sudo howdy add`                |
| Touchscreen       | Manual driver config             | Auto-detected, on-screen keyboard + gestures configured automatically          |
| Monitor bars      | Same bar everywhere              | Hover-reveal glassmorphic bar on primary, minimal pills on secondary, auto-routed per monitor |
| Automation        | Cron jobs, manual scripts        | YAML workflows with AI decision nodes, systemd timers, `costa-flow run`       |
| Usage tracking    | None                             | SQLite query log with cost tracking, budget limits, usage analytics            |
| Cancel AI query   | Close the terminal               | `costa-ai --stop` or click stop button in shell bar widget                     |
| Search your docs  | grep                             | `costa-ai --index ~/docs` then ask questions — RAG-powered retrieval           |

---

## Speed Benchmarks

### AI Navigation (costa-nav)

- **Regex tier** (simple reads): <50ms (free)
- **AT-SPI screen read**: ~200ms (free)
- **Ollama interpretation**: ~3s (free, local)
- **Full conditional plan** (read → decide → act → verify): ~13s (free)
- **Token cost per screen read**: ~82 tokens (vs ~9,180 for screenshot)

### Voice Pipeline

- **Recording**: real-time (Silero VAD auto-stop)
- **Noise reduction**: ~50ms (DeepFilterNet LADSPA)
- **Transcription**: ~500ms (Whisper tiny.en, Vulkan GPU)
- **Local LLM response**: ~1-3s (varies by model tier — 14B is ~1-3s, 3B is ~0.3-1s)
- **End-to-end voice → answer**: ~2-5s

### Model Routing

- **Local query (warm model)**: ~1-3s
- **Auto-escalation to Claude**: ~2-4s additional
- **VRAM tier switch**: ~5-10s (model swap)

---

## Privacy & Cost Model

- **Claude Plan recommended**: Claude Pro ($20/mo) or Max ($100/mo) subscription is the best value for most users — cloud queries are included in your subscription, no per-token billing to worry about
- **API keys for developers**: Programmatic API access also supported for advanced users who need it (typical daily cost ~$0.10-0.50, most queries handled locally)
- **Local-first**: General knowledge, system help, file search, navigation, clipboard analysis, smart commands — all run on-device via Ollama regardless of cloud plan
- **Cloud when needed**: Live web data, code generation, deep research, screenshot analysis escalate to Claude (via Plan or API)
- **No telemetry**: Zero data collection, no usage reporting, no phone-home
- **Credentials stored locally**: API keys and Plan auth stored in `~/.config/costa/env` with `chmod 600`
- **Navigation savings**: 112x token reduction vs screenshot-based agents

---

## Target Users

1. **Anyone tired of fighting Linux** — Costa OS is the easiest Linux distro ever made. If you can describe what you want, Claude Code does it
2. **Developers** who want AI integrated into their workflow, not bolted on as a chat window
3. **Power users** who customize everything and want the OS to learn their patterns
4. **Privacy-conscious users** who want local-first AI with selective cloud escalation
5. **Linux enthusiasts** who want a modern, opinionated Arch setup without the 3-day config marathon
6. **AI researchers** who want to see what a truly AI-native desktop looks like — and contribute to it

---

## System Requirements

| Tier | CPU | RAM | GPU VRAM | Disk | What Works |
|------|-----|-----|----------|------|------------|
| Minimum (cloud-only) | x86_64, 2+ cores | 4GB | Any Vulkan | 20GB | Desktop, AI via Claude (Plan or API), no local LLM, no voice |
| Basic (voice only) | 4+ cores | 8GB | 2GB+ Vulkan | 30GB | Voice transcription (Whisper), cloud AI, no local LLM |
| Recommended (voice + LLM) | 4+ cores | 16GB | 8GB (AMD/NVIDIA) | 40GB | Local 7B model + voice + cloud escalation |
| Full Workstation | 8+ cores | 32GB | 12-16GB+ VRAM | 80GB | Local 14B model resident, gaming + AI simultaneously |

### GPU Capability Tiers

Your GPU VRAM determines the local AI experience. All tiers get the full desktop, voice assistant, and Claude API access — the difference is how much runs locally vs. cloud:

| GPU VRAM | Example GPUs | Local Smart Model | Local AI Quality | Cloud Dependence |
|----------|-------------|-------------------|-----------------|-----------------|
| **No dedicated GPU** | Integrated graphics | None | — | All AI queries go to Claude (via Plan or API) |
| **4GB** | GTX 1650, RX 5500 | qwen2.5:3b | Quick answers, basic reasoning | Moderate — complex queries escalate |
| **8GB** | RTX 3060, RX 6700 | qwen2.5:7b | Good reasoning, system help. costa-nav works well at 7B+ | Low — most queries handled locally |
| **12-16GB** | RTX 4070, RX 7800 XT, RX 9060 XT | qwen2.5:14b | Excellent — handles nearly everything. costa-nav at full accuracy | Minimal — only web search and code gen |
| **24GB+** | RTX 4090, RX 7900 XTX | qwen2.5:32b (~20GB) | Best local intelligence — near cloud quality reasoning, costa-nav at peak accuracy | Minimal |

The VRAM manager automatically detects your GPU and selects the best model. When you launch a game or GPU-heavy app, it steps down or unloads models. When VRAM frees up, it reloads the best model within seconds.

---

## Privacy & Freedom

Costa OS is built on a simple principle: your computer is yours.

- **100% open source** — released under the Apache License 2.0. No proprietary blobs, no closed modules, no "open core" tricks.
- **Zero data collection** — no telemetry, no analytics, no crash reports, no phone-home. Costa OS makes no network calls that you didn't ask for.
- **No accounts required** — ever. No registration, no sign-up, no login. Install and use.
- **Not tied to any company servers** — there are no Costa OS servers. No backend, no cloud dashboard, no corporate infrastructure.
- **All AI processing is local by default** — your questions, commands, and conversations stay on your machine, processed by Ollama on your own GPU.
- **Cloud calls only when you choose** — if you configure your own API keys for Claude or OpenAI, queries go directly from your machine to the provider. Costa OS never proxies, intercepts, or logs them.
- **Voice recordings processed locally and immediately deleted** — audio never leaves your machine. Whisper runs on your GPU, transcribes, and the recording is gone.
- **You own all your data** — conversation history, configs, API keys, everything lives in standard files on your filesystem. Delete it anytime with `rm`.
- **Free as in freedom, free as in beer** — no paid tiers, no premium features, no subscriptions. The full OS is the free version.
- **Fully auditable** — every line of code is on [GitHub](https://github.com/superninjv/costa-os). Read the source, verify the claims, fork it and make it yours.
