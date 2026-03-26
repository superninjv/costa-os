# Costa OS User Guide

*Version 1.0, March 2026*

---

## Table of Contents

1. [Welcome to Costa OS](#1-welcome-to-costa-os)
   - [What Is Costa OS?](#what-is-costa-os)
   - [Philosophy](#philosophy)
   - [What Makes It Different](#what-makes-it-different)
2. [Getting Started](#2-getting-started)
   - [First Boot: What to Expect](#first-boot--what-to-expect)
   - [The Installer Wizard](#the-installer-wizard)
   - [Your First Five Minutes](#your-first-five-minutes)
   - [Essential Keybinds](#essential-keybinds)
   - [Where Things Live](#where-things-live)
3. [The AI Assistant](#3-the-ai-assistant)
   - [Three Ways to Interact](#three-ways-to-interact)
   - [What It Can Do](#what-it-can-do)
   - [How Model Routing Works](#how-model-routing-works)
   - [The Costa Widget](#the-costa-widget)
   - [Reporting Bad Answers](#reporting-bad-answers)
   - [Voice Push-to-Talk](#voice-push-to-talk)
   - [Usage Tracking and Budgets](#usage-tracking-and-budgets)
4. [Desktop and Window Management](#4-desktop-and-window-management)
   - [Understanding Workspaces](#understanding-workspaces)
   - [Moving Windows](#moving-windows)
   - [Tiling, Floating, and Fullscreen](#tiling-floating-and-fullscreen)
   - [Natural Language Window Commands](#natural-language-window-commands)
   - [Multi-Monitor Setup](#multi-monitor-setup)
   - [Window Rules](#window-rules)
5. [Development Environment](#5-development-environment)
   - [Pre-Installed Tools Overview](#pre-installed-tools-overview)
   - [Language Managers](#language-managers)
   - [Containers](#containers)
   - [Claude Code Integration](#claude-code-integration)
   - [Terminal: Ghostty and Zellij](#terminal-ghostty-and-zellij)
   - [Git Workflow](#git-workflow)
6. [Customization](#6-customization)
   - [The Costa Theme](#the-costa-theme)
   - [Changing the Wallpaper](#changing-the-wallpaper)
   - [Shell Bar Modules and Layout](#shell-bar-modules-and-layout)
   - [Adding Keybinds](#adding-keybinds)
   - [Window Rules](#window-rules-1)
   - [Changing Default Applications](#changing-default-applications)
7. [Music and Media](#7-music-and-media)
   - [The Music Widget](#the-music-widget)
   - [Player Controls and Keybinds](#player-controls-and-keybinds)
   - [Cold Starting Music](#cold-starting-music)
   - [Switching Players](#switching-players)
   - [Library Search and Playlists](#library-search-and-playlists)
   - [Volume and Audio Output](#volume-and-audio-output)
8. [System Administration](#8-system-administration)
   - [Installing Packages](#installing-packages)
   - [System Updates](#system-updates)
   - [Managing Services](#managing-services)
   - [Audio Configuration (PipeWire)](#audio-configuration-pipewire)
   - [Network and WiFi](#network-and-wifi)
   - [Bluetooth](#bluetooth)
   - [USB Drives and External Storage](#usb-drives-and-external-storage)
   - [Display and Brightness](#display-and-brightness)
   - [Notifications](#notifications)
9. [Advanced Features](#9-advanced-features)
   - [VRAM Manager](#vram-manager)
   - [Workflows (costa-flow)](#workflows-costa-flow)
   - [Project Management](#project-management)
   - [AI Agents](#ai-agents)
   - [Clipboard Intelligence](#clipboard-intelligence)
   - [Screenshot AI](#screenshot-ai)
   - [Face Authentication](#face-authentication)
   - [Touchscreen Support](#touchscreen-support)
   - [Settings Hub](#settings-hub)
   - [AI Navigation (costa-nav)](#ai-navigation-costa-nav)
   - [Document RAG](#document-rag)
10. [Troubleshooting](#10-troubleshooting)
    - [Common Issues and Fixes](#common-issues-and-fixes)
    - [Where to Find Logs](#where-to-find-logs)
    - [How to Reset Configs](#how-to-reset-configs)
    - [Getting Help](#getting-help)
11. [Privacy and Security](#11-privacy-and-security)
    - [Data Collection Policy](#data-collection-policy)
    - [Where Your Data Lives](#where-your-data-lives)
    - [API Key Management](#api-key-management)
    - [Face Auth Security](#face-auth-security)
    - [Voice Assistant Privacy](#voice-assistant-privacy)
    - [Network Connections Costa OS Makes](#network-connections-costa-os-makes)
12. [Contributing](#12-contributing)
    - [How to Contribute](#how-to-contribute)
    - [Project Structure](#project-structure)
    - [Getting the Source](#getting-the-source)
    - [Filing Issues](#filing-issues)

---

## 1. Welcome to Costa OS

### What Is Costa OS?

Costa OS is a Linux distribution built on Arch Linux and the Hyprland Wayland compositor. Claude Code ships with full system access, so instead of memorizing commands, hunting through settings panels, or reading man pages, you describe what you want, by voice, by typing, or through keybinds, and the system does it. It knows your hardware, your running processes, your configs, and your project contexts.

Under the hood, Costa OS is a fully-featured Arch Linux installation with a tiling window manager, a curated set of development tools, and a custom Mediterranean-inspired theme called "Costa." What makes it different is that Claude Code and local models are connected to every component. The clipboard watches what you copy and offers to debug errors. The screenshot tool analyzes images on capture. The music player, window manager, notification system, and status bar all feed into the same routing system.

Costa OS is powered by Claude Code in combination with a local model running on your GPU. Claude Code ships with full system access and handles complex tasks like code generation, debugging, system management, and multi-step workflows. The local model handles routine queries (system status, quick lookups, simple commands) with instant responses and no internet needed. Routing between them is automatic. When cloud AI is used, your queries go directly to Anthropic. Costa OS has no servers in the middle. There is no telemetry, no analytics, and no accounts.

### Philosophy

Costa OS is built on three principles:

**1. Describe what you want, the system does it.** Traditional operating systems force you to learn their language: command flags, config file syntax, menu hierarchies. Costa OS lets you skip that. Want to install a program? Say "install Blender." Want to change a keybind? Say "bind Super+G to open GIMP." Want to know why your build is slow? Ask, and the system checks your CPU load, running containers, swap usage, and compiler flags before answering.

**2. Claude Code at the center, local models for speed.** Claude Code is the primary intelligence: it can modify any config, install any package, write any script, and navigate graphical applications on your behalf. Local models running on your GPU handle routine queries with sub-second latency and zero internet dependency. The two work together: local for fast, private, everyday tasks; Claude for anything that requires real reasoning. Your data stays private regardless: Costa OS has no servers, no telemetry, and no accounts.

**3. Maximum customization, zero gatekeeping.** Costa OS is your machine. Every config file is documented, every tool is replaceable, and the entire codebase is open source under the Apache License 2.0. The AI makes customization effortless for beginners, and the underlying Arch Linux foundation means power users can go as deep as they want.

### What Makes It Different

Most Linux distributions hand you a desktop and leave you to figure out the rest. Costa OS is different in several concrete ways:

- **Claude Code is your system administrator.** It ships as a first-class citizen with full system access, 30+ MCP tools, and a hardware-aware context file generated at first boot. It can modify any config, install any package, create any script, navigate graphical applications, and debug problems end-to-end. Just describe what you want in plain English.

- **The AI knows your actual system.** Every query is enriched with live data: running processes, GPU utilization, disk space, network state, audio routing, window layout. When the AI answers, it answers about *your* machine, not a generic one.

- **Two tiers work together.** Claude Code handles complex tasks: code generation, multi-file edits, architecture, debugging. Local models on your GPU handle routine queries (system status, quick lookups, simple commands) with sub-second latency and zero internet dependency. Routing between them is automatic.

- **The entire desktop is AI-aware.** Copy an error message and the clipboard service offers to debug it with AI. Take a screenshot and the AI reads and analyzes it. The voice assistant transcribes speech in 500 milliseconds. Shell bar modules show AI status, usage metrics, and processing indicators.

- **It is still Arch Linux.** Underneath the AI layer, this is a standard Arch installation. `pacman` works. `systemctl` works. You have full root access. Nothing is locked down, hidden, or "simplified" by removing functionality. The AI is an addition, not a restriction.

---

## 2. Getting Started

### First Boot. What to Expect

When you boot the Costa OS ISO for the first time, you will see a graphical installer. This is a GTK4 application that walks you through disk partitioning, user account creation, and initial configuration. No terminal is required during installation.

After installation and reboot, the system runs a first-boot wizard that:

1. **Sets up Claude Code**: prompts you to authenticate with your Anthropic account (Claude Pro, Max, or API key). This is the first step because once Claude Code is working, it can help fix anything else that goes wrong during setup.
2. Detects your GPU and installs the appropriate drivers (AMD, NVIDIA, or Intel)
3. Detects your monitors and generates a multi-monitor AGS shell configuration
4. Generates a hardware-aware `CLAUDE.md` so Claude Code knows your exact setup
5. Detects optional hardware (IR camera for face auth, touchscreen for gestures)
6. Pulls the best local AI model your GPU can handle from Ollama (for fast, offline queries)
7. Builds Whisper.cpp with GPU acceleration for voice transcription
8. Optionally sets up face authentication and touchscreen gestures

This process takes a few minutes depending on your internet speed and GPU. Claude Code authentication happens first so that if any subsequent step fails, you can immediately ask Claude Code to diagnose and fix it. When setup finishes, you land on a fully configured desktop with the Costa theme, shell bar panels on every monitor, and both Claude Code and the local AI assistant ready to use.

<!-- screenshot: The Costa OS desktop after first boot, showing the AGS shell bar at the top with the Costa AI widget, now-playing module, and system tray. The desktop shows the Costa default wallpaper with the Costa theme. -->

### The Installer Wizard

The ISO boots directly into a GTK4 graphical installer called `costa-install-gui`. It supports three partition modes:

| Mode | Description | Best For |
|------|-------------|----------|
| **Erase entire disk** | Formats the selected disk and installs Costa OS as the only operating system | New machines, dedicated Linux setups |
| **Install alongside** | Resizes an existing partition to make room for Costa OS, sets up dual-boot | Keeping Windows or another OS |
| **Manual partitioning** | You select which partitions to use for root, home, boot, and swap | Advanced users with specific layouts |

The installer handles all of the low-level work: formatting, mounting, pacstrap, bootloader installation, and initial configuration. When it finishes, you remove the USB drive and reboot into your new system.

<!-- screenshot: The Costa OS installer showing the partition mode selection screen with three large buttons for Erase, Alongside, and Manual. -->

### Your First Five Minutes

After the first-boot wizard completes, here is what to do:

1. **Open a terminal.** Press `SUPER+Enter`. This launches Ghostty, the GPU-accelerated terminal, pre-configured with the Costa theme and JetBrains Mono Nerd Font.

2. **Open the app launcher.** Press `SUPER+Space`. This opens Rofi, a fuzzy-search launcher. Start typing the name of any application and press Enter to launch it. For example, type "firefox" and press Enter to open the browser.

3. **Try the AI assistant.** In the terminal, type:
   ```bash
   costa-ai "what GPU do I have"
   ```
   The AI will check your actual hardware and respond with the model name, driver version, and VRAM amount. This is a local query, it never touches the internet.

4. **Try voice input.** Hold `SUPER+ALT+V` and speak a question. For example: "What packages do I have installed for Python?" Release the key when you finish speaking. The audio is transcribed locally by Whisper, then sent to the AI for a response.

5. **Move between workspaces.** Press `SUPER+1` through `SUPER+4` to switch between the four main workspaces on your primary monitor. If you have additional monitors, `SUPER+5` and `SUPER+6` switch to workspaces on those screens.

6. **Open the settings hub.** Press `SUPER+I` or click the gear icon in the shell bar. This is where you configure monitors, manage AI models, set up face auth, enter API keys, and more.

<!-- screenshot: A terminal showing the output of 'costa-ai "what GPU do I have"' with the AI response listing the detected GPU model, driver, and VRAM. -->

### Essential Keybinds

These are the keybinds you will use most often. Costa OS uses vim-style navigation with the `SUPER` key (also called the Windows key or Meta key) as the primary modifier.

#### Applications

| Keybind | Action |
|---------|--------|
| `SUPER+Enter` | Open terminal (Ghostty) |
| `SUPER+B` | Open browser (Firefox) |
| `SUPER+E` | Open file manager (Thunar) |
| `SUPER+Space` | Open app launcher (Rofi) |
| `SUPER+Q` | Close the focused window |
| `SUPER+I` | Open Settings Hub |

#### Window Focus and Movement

| Keybind | Action |
|---------|--------|
| `SUPER+H` | Focus the window to the left |
| `SUPER+J` | Focus the window below |
| `SUPER+K` | Focus the window above |
| `SUPER+L` | Focus the window to the right |
| `SUPER+SHIFT+H/J/K/L` | Move the focused window in that direction |
| `SUPER+CTRL+H/J/K/L` | Resize the focused window |

#### Window States

| Keybind | Action |
|---------|--------|
| `SUPER+F` | Toggle fullscreen |
| `SUPER+SHIFT+F` | Toggle floating (detach window from tiling) |

#### Workspaces

| Keybind | Action |
|---------|--------|
| `SUPER+1` through `SUPER+6` | Switch to that workspace |
| `SUPER+SHIFT+1` through `SUPER+SHIFT+6` | Move the focused window to that workspace |

#### AI and Voice

| Keybind | Action |
|---------|--------|
| `SUPER+ALT+V` | Voice command: Claude mode (AI processes your speech and responds) |
| `SUPER+ALT+B` | Voice command: Type mode (transcribes speech and types into the focused window) |

#### Media and Utilities

| Keybind | Action |
|---------|--------|
| `SUPER+]` | Next track |
| `SUPER+[` | Previous track |
| `SUPER+\` | Play/pause |
| `SUPER+V` | Clipboard history |
| `Print` | Screenshot region to file |
| `SUPER+Print` | Screenshot region to clipboard |
| `SUPER+SHIFT+A` | AI screenshot (select region, get AI analysis) |
| `SUPER+SHIFT+T` | OCR screenshot (select region, extract text) |

If you ever forget a keybind, you can ask the AI: `costa-ai "what is the keybind for fullscreen"` or use the keybind configurator: `costa-keybinds list`.

### Where Things Live

Costa OS follows standard Linux conventions for configuration. Here is where the important files are:

| Path | What It Contains |
|------|-----------------|
| `~/.config/hypr/hyprland.conf` | Hyprland window manager configuration (keybinds, monitors, window rules) |
| `~/.config/hypr/monitors.conf` | Auto-generated monitor layout (positions, resolutions, refresh rates) |
| `~/.config/ags/config.js` | AGS shell bar layout (which modules appear, in what order) |
| `~/.config/ags/style.css` | AGS shell bar styling (colors, sizes, fonts) |
| `~/.config/ghostty/config` | Terminal configuration (font, colors, opacity) |
| `~/.config/rofi/config.rasi` | App launcher theme and behavior |
| `~/.config/dunst/dunstrc` | Notification daemon configuration (position, colors, timeout) |
| `~/.config/costa/config.json` | Costa AI main configuration |
| `~/.config/costa/env` | API keys (mode 600, owner-read only) |
| `~/.config/costa/knowledge/` | Knowledge base files the AI uses to answer questions |
| `~/.config/costa/workflows/` | Workflow automation definitions (YAML) |
| `~/.config/costa/projects/` | Project context configs for workspace switching |
| `~/.config/costa/agents/` | Custom AI agent definitions |
| `~/.config/costa/costa.db` | SQLite database for query history, usage stats, and costs |
| `~/.config/costa/gpu.conf` | Detected GPU information |

You do not need to memorize these paths. The AI knows all of them, and you can always ask: `costa-ai "where is the shell bar config"`.

---

## 3. The AI Assistant

The AI assistant is the heart of Costa OS. It is not a chatbot bolted onto the side, it is deeply integrated into every part of the system, with access to live system state, 30+ structured tools, and the ability to execute safe commands automatically.

### Three Ways to Interact

There are three input methods, and they all feed into the same intelligence layer:

**1. Terminal (CLI)**

The `costa-ai` command lets you ask questions and give commands directly from any terminal:

```bash
costa-ai "what services are using the most memory"
costa-ai "install htop"
costa-ai "why is my fan running so loud"
costa-ai "write me a Python HTTP server"
```

This is the most versatile method. It supports flags for JSON output, history browsing, usage stats, and more.

**2. Voice (Push-to-Talk)**

Hold `SUPER+ALT+V` and speak your question or command naturally. Release when you are done talking. The system records your audio, reduces background noise with DeepFilterNet, detects when you stop speaking with Silero VAD, transcribes your speech with Whisper on your GPU, and sends the text to the AI. The entire pipeline runs locally.

There is also a Type mode (`SUPER+ALT+B`) that transcribes your speech and types the resulting text directly into whatever window is focused, useful for dictation into text fields, documents, or chat apps.

**3. Shell Bar Widget (Text Input)**

Left-click the Costa icon in the center of the shell bar to open a Rofi text input box. Type your question and press Enter. This is useful when you want to interact with the AI without opening a terminal or using your voice.

Right-click the Costa icon to see the full text of the last AI response.

<!-- screenshot: The three interaction methods side by side: a terminal with costa-ai output, the shell bar Costa icon with a Rofi text input dropdown, and the shell bar showing a voice processing indicator. -->

### What It Can Do

The AI assistant is not limited to answering questions. It can take actions on your system, and it knows the difference between safe and dangerous operations.

**Information queries**: The AI gathers live system data before answering:

```bash
costa-ai "what is using my GPU right now"      # checks GPU utilization
costa-ai "is Docker running"                    # checks systemctl and docker ps
costa-ai "what Python packages are installed"   # queries pacman
costa-ai "what is my IP address"                # checks ip addr and curl ifconfig.me
```

**System actions**: Safe commands execute automatically:

```bash
costa-ai "turn up the volume to 80%"           # runs wpctl
costa-ai "skip this track"                      # runs playerctl
costa-ai "switch to workspace 3"                # runs hyprctl
costa-ai "set brightness to 50%"                # runs brightnessctl
```

**Ask-first actions**: Potentially destructive commands require your confirmation:

```bash
costa-ai "install Blender"                      # shows 'sudo pacman -S blender', asks before running
costa-ai "restart the Ollama service"            # shows 'systemctl restart ollama', asks first
costa-ai "change my terminal font to Fira Code"  # shows the config change, asks before applying
```

**Blocked actions**: Dangerous commands are never auto-executed:

Commands involving `rm -rf`, `dd`, `mkfs`, `shutdown`, and similar destructive operations are always flagged. The AI will explain what the command would do and ask you to run it yourself if you really want to.

**Web-augmented queries**: When local models cannot answer (live news, current events, real-time data), the query escalates to Claude with web search:

```bash
costa-ai "what is the latest Linux kernel version"
costa-ai "what is the weather in Boston"         # fetches from wttr.in
costa-ai "who won the game last night"
```

**Code generation**: Complex coding questions route to Claude Sonnet:

```bash
costa-ai "write a Rust function that parses CSV files"
costa-ai "debug this Python traceback: [paste error]"
costa-ai "explain what this regex does: ^(?:(?:25[0-5]|...))"
```

### How Model Routing Works

When you ask a question, the AI router analyzes your query and picks the best model to answer it. You never need to think about this, it happens automatically. But understanding the system helps you appreciate why some answers are instant and others take a few seconds.

**Local models** run on your GPU and process queries without any internet connection. They are fast and private. The VRAM manager keeps the largest model your GPU can fit loaded in memory at all times:

| Available VRAM | Model Loaded | Quality |
|---------------|-------------|---------|
| 12GB+ | qwen2.5:14b | Best local quality: handles most queries without cloud |
| 6--12GB | qwen2.5:7b | Good quality, occasional cloud escalation |
| 3--6GB | qwen2.5:3b | Fast basic answers, more cloud escalation |
| <3GB (gaming) | None loaded | All queries go to cloud |

**Cloud models** are used when the local model cannot answer or when the query requires capabilities the local model does not have:

| Model | Used For | Latency |
|-------|----------|---------|
| Claude Haiku | Live news, weather, real-time web data | ~2--4 seconds |
| Claude Sonnet | Code generation, debugging, multi-file edits | ~3--5 seconds |
| Claude Opus | Deep research, architecture review, security audit | ~5--10 seconds |

**Auto-escalation** is the key feature that makes this seamless. If the local model responds with "I don't know" or similar uncertainty phrases, the router automatically re-sends your query to Claude Haiku with web search capability. You do not need to retry or specify a different model. The system detects uncertainty using 15+ pattern-matching rules and handles it silently.

#### Neural Routing (ML Router)

Behind the pattern matching, Costa OS uses a lightweight PyTorch neural network to learn which model handles which queries best. This is a 3-layer MLP classifier (Input→64→32→7 classes) that runs in under 1ms on CPU.

**How it works:**

1. Your query is converted into a 29-dimension feature vector: query length, word count, question mark presence, action/code/web keyword detection, time of day, current VRAM tier, and 21 topic-pattern match flags.
2. The neural network predicts one of 7 route classes: `local`, `local_will_escalate`, `haiku+web`, `sonnet`, `opus`, `file_search`, or `window_manager`.
3. If confidence exceeds 65%, the ML prediction is used. Otherwise, the system falls back to regex pattern matching.
4. The model auto-retrains every 50 queries in the background, incorporating your real usage data (weighted 3x higher than synthetic training samples) alongside ~300+ synthetic labeled examples.

**Training the router:**

```bash
python3 ai-router/ml_router.py train              # generate synthetic data + train
python3 ai-router/ml_router.py eval               # train + evaluate + print accuracy report
python3 ai-router/ml_router.py predict "query"    # test route prediction for a query
```

The trained model is saved to `~/.config/costa/ml_router.pt`. It is small (a few KB) and loads instantly. If no trained model exists, the system falls back gracefully to regex-only routing with no degradation in functionality.

**Self-improving routing:** Every query you make is logged to the local SQLite database with the model used, whether escalation occurred, and timing data. When you report a bad answer (see below), the routing decision is marked as incorrect. This feedback is used in the next training cycle, so the neural router literally learns from your corrections over time.

You can override routing when needed:

```bash
costa-ai --no-escalate "quick question"        # force local only, never use cloud
costa-ai --model opus "architecture review"     # force a specific cloud model
costa-ai --preset code "refactor this function"  # bias toward code-optimized routing
costa-ai --preset fast "what time is it"        # bias toward speed, minimal context
```

### The Costa Widget

The Costa widget in the shell bar is the visual control center for the AI assistant. It sits in the center of the top bar on your primary monitor and provides at-a-glance status plus quick actions.

**Visual indicators:**

- Idle state: the Costa icon is displayed normally
- Processing: a spinner appears while the AI is working on your query
- Response: the answer scrolls across the bar as text

**Mouse actions:**

| Action | What It Does |
|--------|-------------|
| Left-click | Opens a Rofi text input: type your question and press Enter |
| Right-click | Shows the full text of the last AI response |
| Middle-click | Opens the stop button to cancel a running query |

There is also a report button (the 󰚑 icon) that appears after a response, which you can click to report a bad answer. More on that below.

### Reporting Bad Answers

Local AI models are not perfect. When the AI gives you a wrong answer, you can report it, and the system will correct itself:

1. Click the 󰚑 (report) icon in the shell bar after receiving a bad answer.
2. The failed query and response are sent to Claude Haiku.
3. Claude identifies what went wrong, missing knowledge, wrong context, or hallucination.
4. Claude generates a patch for the relevant knowledge file in `~/.config/costa/knowledge/`.
5. The patch is applied automatically.
6. The routing decision is marked as incorrect in the database, feeding into the ML router's next training cycle.
7. A notification shows you the corrected answer.
8. Next time anyone asks the same question, the local model has the updated knowledge, and the neural router knows to pick a better model.

Corrections are logged in `~/.config/costa/knowledge/.corrections.json`. You can review all corrections with:

```bash
costa-ai-report corrections
```

This creates a dual feedback loop: knowledge files are patched so the local model has better reference material, and the neural routing classifier learns from incorrect routing decisions so queries are sent to the right model in the first place. Both improvements happen automatically without retraining the underlying language model.

### Voice Push-to-Talk

The voice assistant uses a push-to-talk model. You hold a key to record, and release it when done. There is no always-on listening, the microphone is only active while you hold the key.

**Two modes:**

| Keybind | Mode | What Happens |
|---------|------|--------------|
| `SUPER+ALT+V` | Claude mode | AI processes your command and responds via notification |
| `SUPER+ALT+B` | Type mode | Transcribes your speech and types it into the focused window |

**How it works:**

1. Hold the key and speak normally.
2. Audio is captured from your microphone and processed through DeepFilterNet, which crushes background noise from ~0.2 RMS to ~0.004 RMS.
3. Silero VAD (Voice Activity Detection) automatically detects when you stop speaking. You do not need to release the key at the exact moment you stop talking, the system handles this.
4. Whisper tiny.en transcribes your speech on the GPU in about 500 milliseconds.
5. The transcribed text is sent to the AI router, which picks the best model and responds.
6. The response appears as a scrolling notification in the shell bar and as a Dunst notification popup.

**Auto-submit control:**

By default, commands auto-execute. If you want to review the transcription before it is submitted, say the word **"draft"** or **"hold"** anywhere in your sentence. The transcribed text will appear for review instead of executing.

**Troubleshooting voice issues:**

```bash
cat /tmp/ptt-voice-status     # check current PTT state
cat /tmp/ptt-voice-output     # check last transcription/response
wpctl status                  # verify microphone is the default source
ollama ps                     # check if a model is loaded
```

| Problem | Solution |
|---------|----------|
| No audio captured | Run `wpctl status` and check that your microphone is the default source |
| Transcription is garbage | Background noise is too high: verify DeepFilterNet is running in the pipeline |
| VAD never stops recording | Silero VAD needs DeepFilterNet preprocessing to work properly |
| Slow response | The model may not be loaded: check `ollama ps` and `$XDG_RUNTIME_DIR/costa/ollama-smart-model` |
| Nothing happens on keypress | Verify the keybind exists: `hyprctl binds \| grep ALT+V` |

### Usage Tracking and Budgets

Every AI query is logged to a local SQLite database (`~/.config/costa/costa.db`) with the model used, latency, token counts, and cost estimates. Nothing is sent anywhere, this is purely local analytics.

```bash
costa-ai --history                 # browse past queries and responses
costa-ai --search "docker"         # full-text search through query history
costa-ai --usage                   # usage statistics by model, time, and cost
```

If you use cloud models and want to control spending:

```bash
costa-ai --budget 5.00             # set a daily spending limit of $5
costa-ai --budget 0.50 day         # $0.50/day cap
costa-ai --budget 30.00 month      # $30/month cap
```

When the budget is exhausted, all queries fall back to local models only. Cloud escalation is blocked until the budget period resets.

---

## 4. Desktop and Window Management

Costa OS uses Hyprland, a modern Wayland tiling compositor. If you have used i3, Sway, or other tiling window managers, many concepts will be familiar. If this is your first tiling WM, the key idea is simple: windows automatically arrange themselves to fill the screen, and you move between them with keyboard shortcuts instead of clicking and dragging.

### Understanding Workspaces

Workspaces are virtual desktops. Instead of stacking all your windows on one screen, you spread them across numbered workspaces and switch between them instantly. Think of them as separate rooms in your house, your code editor is in room 1, your browser is in room 2, your music player is in room 3.

Costa OS configures workspaces per-monitor:

| Workspace | Monitor | Typical Use |
|-----------|---------|-------------|
| 1--4 | Primary monitor (highest resolution/refresh rate) | Main working area |
| 5--6 | Secondary monitors | Reference material, media, chat |
| 7 | Virtual headless monitor (Claude Code's workspace) | AI navigation: invisible |

Switch workspaces with `SUPER+<number>`. Move a window to a workspace with `SUPER+SHIFT+<number>`.

If you have a single monitor, all workspaces live on that one screen and you simply switch between them. The system auto-detects your monitor configuration and assigns workspaces appropriately.

### Moving Windows

**Keyboard (vim-style):**

| Action | Keybind |
|--------|---------|
| Focus left/down/up/right | `SUPER+H/J/K/L` |
| Move window left/down/up/right | `SUPER+SHIFT+H/J/K/L` |
| Resize window | `SUPER+CTRL+H/J/K/L` |
| Move window to workspace N | `SUPER+SHIFT+N` |

**Between monitors:**

To move a window to a different monitor, move it to a workspace that lives on that monitor. For example, if workspace 5 is on your top monitor, pressing `SUPER+SHIFT+5` moves the focused window there.

You can also use hyprctl commands directly:

```bash
hyprctl dispatch movewindow mon:HDMI-A-2       # move to a specific monitor
hyprctl dispatch focusmonitor DP-1              # focus a specific monitor
```

**With the AI:**

```bash
costa-ai "move firefox to the top monitor"
costa-ai "put the terminal on workspace 2"
costa-ai "tile the editor and terminal side by side"
```

### Tiling, Floating, and Fullscreen

By default, windows tile automatically, they split the available space evenly. There are three window modes:

**Tiled** (default): Windows automatically arrange themselves in the available space. When you open a new window, existing windows shrink to make room.

**Floating**: The window is detached from tiling and can be freely positioned and resized with the mouse. Toggle with `SUPER+SHIFT+F`. Some windows float by default (settings dialogs, popup windows, the music widget).

**Fullscreen**: The window takes up the entire screen, covering the shell bar. Toggle with `SUPER+F`. There are actually three fullscreen modes:
- `SUPER+F`: true fullscreen (covers everything)
- Maximize mode, fills the monitor but keeps gaps and shell bar visible

To move or resize a floating window with the mouse, hold `SUPER` and drag with the left mouse button (move) or right mouse button (resize).

### Natural Language Window Commands

One of Costa OS's distinctive features is the ability to manage windows with natural language through the AI:

```bash
costa-ai "move firefox to workspace 3"
costa-ai "put the terminal on the left monitor"
costa-ai "make VS Code fullscreen"
costa-ai "float the file manager"
costa-ai "close all terminals"
costa-ai "tile the editor on the left and terminal on the right"
```

The AI translates these into `hyprctl` commands and executes them. It knows your monitor layout, window positions, and application names.

### Multi-Monitor Setup

Costa OS auto-detects monitors during first boot and generates optimal configurations. If you add or remove monitors later:

1. Open the Settings Hub (`SUPER+I` or `costa-settings`)
2. Go to Display and click "Detect Monitors"
3. The system re-scans, updates `~/.config/hypr/monitors.conf`, and regenerates AGS shell configs

Or from the terminal:

```bash
hyprctl monitors                                           # see current monitor layout
~/.config/costa/scripts/generate-ags-config.sh             # regenerate AGS shell for new monitors
```

Each monitor gets an appropriate AGS shell configuration automatically:
- **Primary** (highest refresh rate, then resolution) gets the full-featured main bar with all modules
- **First secondary** gets a performance monitoring bar (GPU, CPU, temperatures)
- **Additional secondaries** get minimal bars (workspaces and clock)
- **Headless virtual monitor** (if present) gets Claude's screen bar

To manually configure a monitor, edit `~/.config/hypr/hyprland.conf`:

```ini
monitor = DP-1, 2560x1440@165, 0x0, 1
monitor = HDMI-A-1, 1280x720, -720x0, 1, transform, 1
monitor = HDMI-A-2, 1920x1080@60, 320x-1080, 1
```

The format is: `monitor = NAME, WIDTHxHEIGHT@REFRESH, X_POSITION x Y_POSITION, SCALE, transform, ROTATION`.

After editing, reload with `hyprctl reload`.

### Window Rules

Window rules let you customize how specific applications behave. For example, you might want a calculator to always float, or a music player to always open on workspace 5.

Rules go in `~/.config/hypr/hyprland.conf`:

```ini
# Make Rofi and pavucontrol always float
windowrule = float, class:^(rofi|pavucontrol)$

# Set terminal transparency
windowrule = opacity 0.9, class:^(ghostty)$

# Open Firefox on workspace 2
windowrule = workspace 2, class:^(firefox)$

# Set default size for calculator
windowrule = size 400 600, class:^(org.gnome.Calculator)$

# Float and center the music widget
windowrule = float, class:^(costa-music)$
windowrule = center, class:^(costa-music)$
```

To find the class name of any window:

```bash
hyprctl clients -j | jq '.[].class'
```

Or ask the AI: `costa-ai "what is the window class for spotify"`.

After editing, reload with `hyprctl reload`, no restart needed.

---

## 5. Development Environment

Costa OS comes pre-configured with a comprehensive development setup. Everything is installed and ready to use, with sensible defaults that you can customize as needed.

### Pre-Installed Tools Overview

| Category | Tools |
|----------|-------|
| **Editors** | VS Code (with extension suite), terminal editors via `$EDITOR` |
| **Terminal** | Ghostty (GPU-accelerated), Zellij (multiplexer) |
| **Languages** | Python (pyenv), Node.js (nvm), Java (SDKMAN), Rust (rustup) |
| **Containers** | Docker, docker-compose, lazydocker, kubectl, k9s |
| **Git** | Git (with delta pager), lazygit (TUI), GitHub CLI (`gh`) |
| **Search/Navigate** | fd (find), ripgrep (grep), fzf (fuzzy finder), eza (ls) |
| **System** | btm (system monitor), procs (processes), dust (disk usage), bandwhich (network) |
| **HTTP** | xh (curl alternative for APIs) |
| **Code** | tokei (line counter), sd (find-and-replace), bat (cat with syntax highlighting) |
| **AI** | Claude Code (with MCP tools, custom commands, virtual monitor) |

### Language Managers

Costa OS uses version managers for each language, so you can switch between versions without conflicts:

**Python (pyenv)**

```bash
pyenv install 3.12              # install a specific version
pyenv global 3.12               # set the default version
pyenv shell 3.11                # use a specific version in this shell
pyenv versions                  # list installed versions
```

**Node.js (nvm)**

```bash
nvm install 24                  # install Node 24
nvm use 24                      # use Node 24 in this shell
nvm alias default 24            # set the default version
nvm ls                          # list installed versions
```

**Java (SDKMAN)**

```bash
sdk install java 21-open        # install Java 21
sdk use java 21-open            # use Java 21 in this shell
sdk default java 21-open        # set the default version
sdk list java                   # list available versions
```

**Rust (rustup)**

```bash
rustup update                   # update the toolchain
rustup default stable           # use the stable channel
rustup target add wasm32-unknown-unknown   # add a compilation target
```

### Containers

Docker and container tools are pre-installed and ready:

```bash
docker compose up -d            # start services defined in docker-compose.yml
docker compose down             # stop services
docker ps                       # list running containers
lazydocker                      # TUI for managing Docker containers and images
```

For Kubernetes:

```bash
kubectl get pods                # list pods
kubectl apply -f manifest.yaml  # apply a manifest
k9s                             # TUI for managing Kubernetes clusters
```

### Claude Code Integration

Claude Code is not just installed on Costa OS, it is a first-class citizen with deep system integration.

**Launching Claude Code:**

```bash
claude                          # from any terminal
```

Or left-click the 󰚩 icon in the shell bar.

**Shell bar controls for Claude Code:**

| Mouse Action | What It Does |
|-------------|-------------|
| Left-click 󰚩 | Launch Claude Code |
| Right-click 󰚩 | Model picker (switch between Sonnet and Opus) |
| Scroll on 󰚩 | Cycle through project contexts |
| Middle-click 󰚩 | Dangerous mode (auto-approve all actions: use carefully) |

**Custom slash commands** ship pre-configured:

| Command | Description |
|---------|-------------|
| `/check-system` | Audit system health: services, disk, memory, GPU |
| `/configure-shell` | Modify AGS shell configuration with guidance |
| `/install` | Install and configure a package with AUR fallback |
| `/theme` | Apply or modify Costa theme elements |
| `/troubleshoot` | Diagnose and fix system issues |

**MCP server tools** give Claude Code direct access to your system:

Claude Code has 30+ tools available through the Costa OS MCP server (`costa-system`), including reading processes and services, managing windows via Hyprland, opening browsers and navigating URLs, controlling media playback, taking screenshots, and reading/writing files. These tools are used automatically when relevant to your request.

**Virtual monitor:**

Claude Code operates on an invisible virtual headless monitor (HEADLESS-2, workspace 7, 1920x1080). It can open its own browser, navigate pages, fill forms, and research, all without interrupting your screen. This uses a proprietary MCP navigation system under development for screen reading, which is 112x cheaper in tokens than screenshot-based approaches.

To see what Claude is doing on its virtual monitor, click the 󰍹 icon in the shell bar. This toggles a live preview window that auto-refreshes every 2 seconds.

**Knowledge base:**

21 topic-specific knowledge files are available as MCP resources. When Claude Code answers a question about audio, it loads `pipewire-audio.md`. When it answers about packages, it loads `arch-admin.md`. This means Claude Code has deep, up-to-date knowledge about your exact system configuration.

### Terminal: Ghostty and Zellij

**Ghostty** is the default terminal emulator. It is GPU-accelerated, meaning it renders text faster than traditional terminals, which matters when scrolling through large build outputs or log files. It is pre-configured with the Costa theme and JetBrains Mono Nerd Font.

Configuration: `~/.config/ghostty/config`

Note: Ghostty does not support hot-reloading. Close and reopen the terminal to apply config changes.

**Zellij** is the terminal multiplexer (similar to tmux or screen). It lets you split your terminal into panes and tabs:

```bash
zellij                          # start a new session
```

Key shortcuts inside Zellij:
- `Ctrl+T`: new tab
- `Ctrl+N`: new pane
- `Ctrl+P`: switch to pane mode (then use arrow keys)
- `Ctrl+O`: switch to session mode

### Git Workflow

Git is configured with quality-of-life improvements:

**Delta pager**: `git diff` shows beautiful side-by-side diffs with syntax highlighting and line numbers, instead of the default unified diff format.

**lazygit**: A terminal UI for Git that makes staging, committing, branching, and rebasing visual and fast. Launch with:

```bash
lazygit
```

**GitHub CLI**: The `gh` command is pre-installed and authenticated (if you set it up during first boot):

```bash
gh pr create                    # create a pull request
gh pr view                      # view the current PR
gh issue list                   # list open issues
gh repo clone owner/repo        # clone a repository
```

Your SSH key lives at `~/.ssh/id_ed25519`.

---

## 6. Customization

### The Costa Theme

The Costa theme is a custom Mediterranean coastal palette with a dark base and warm, ocean-inspired accents. It is applied consistently across every component of the system.

| Color | Hex | Role |
|-------|-----|------|
| Base | `#1b1d2b` | Background: deep navy |
| Surface | `#252836` | Panels, cards, elevated surfaces |
| Text | `#d4cfc4` | Primary text: warm white |
| Sea | `#5b94a8` | Primary accent: teal blue |
| Terracotta | `#c07a56` | Secondary accent: warm orange |
| Foam | `#7eb5b0` | Light accent: soft teal |
| Sand | `#c9a96e` | Highlight: golden |
| Olive | `#8b9968` | Positive/success: muted green |
| Lavender | `#9884b8` | Decorative: purple |
| Rose | `#b87272` | Error/urgent: muted red |

These colors are defined in multiple places to ensure consistency:

| Component | Where Colors Are Defined |
|-----------|-------------------------|
| Hyprland | Variables like `$sea`, `$foam`, `$terracotta` in `hyprland.conf` |
| AGS shell | Color definitions in `~/.config/ags/style.css` |
| Rofi | Color definitions in `~/.config/rofi/config.rasi` |
| Ghostty | Palette entries in `~/.config/ghostty/config` |
| GTK apps | CSS overrides in Costa's libadwaita apps |
| Dunst | Color values in `~/.config/dunst/dunstrc` |

The system-wide GTK theme is `adw-gtk3-dark`, icons are `Papirus-Dark`, and the cursor is `Bibata-Modern-Ice`. The font is `JetBrains Mono Nerd Font` everywhere.

### Changing the Wallpaper

Costa OS ships with static Costa-themed wallpapers set via `swww`. It also supports animated video wallpapers through `mpvpaper`.

**Through the Settings Hub:**

1. Open Settings Hub (`SUPER+I`)
2. Go to Display, then Wallpaper
3. Browse local files or paste a path
4. Supported formats: static images (PNG, JPG), videos (MP4, WebM), Wallpaper Engine scenes

**Through the terminal:**

```bash
# Set a video wallpaper on all monitors
mpvpaper '*' /path/to/video.mp4 --fork

# Set a static wallpaper
swww img /path/to/image.jpg
```

To change the default wallpaper that loads at startup, edit `~/.config/costa/scripts/wallpaper.sh`.

**Wallpaper Engine** (optional): If you have Wallpaper Engine on Steam, you can use those wallpapers:

```bash
# Install the engine
yay -S linux-wallpaperengine-git

# Run a scene
linux-wallpaperengine --screen-root '*' /path/to/scene/
```

Video and 2D scenes work well. Complex 3D scenes may crash on some GPUs.

If you use a video wallpaper, it includes a smart pause feature: it automatically pauses the animation when windows cover more than 37.5% of the desktop, saving GPU resources.

### Shell Bar Modules and Layout

The AGS shell bar is the status bar at the top of each monitor. It contains 16+ modules that show system information and provide quick actions.

| Module | What It Does |
|--------|-------------|
| now-playing | Shows current track and artist, click to open music widget |
| PTT button | Voice assistant status, click for text input |
| costa-ai | Active model, processing status, stop button |
| Claude Code launcher | Launch, model pick, project cycle |
| Headless preview | Toggle live preview of Claude's virtual monitor |
| Docker status | Running container count |
| Weather | Current conditions |
| Git status | Branch and dirty state for current project |
| SSH quick-connect | One-click server connections |
| System updates | Available package update count |
| Network speed | Live upload/download rates |
| Project switcher | Switch project context via Rofi |
| Pomodoro timer | Focus timer with notifications |
| Keybinds configurator | Launch keybinds GUI |
| Settings | Launch settings hub |
| Power menu | Logout, reboot, shutdown |

**Bar templates** are assigned per monitor:

| Template | Used On | Content |
|----------|---------|---------|
| main-bar | Primary monitor | All modules: full control surface |
| performance-bar | First secondary | GPU, CPU, RAM, disk, temperature monitoring |
| minimal-bar | Additional secondaries | Workspaces and clock only |
| taskbar | Same as performance-bar | Window list |
| claude-screen-bar | Headless monitor | Minimal bar for Claude's virtual display |

**Regenerating shell bar config** (after adding/removing monitors):

```bash
~/.config/costa/scripts/generate-ags-config.sh
ags quit; ags run &disown
```

**Customizing modules:**

1. Edit template files in `~/.config/ags/templates/` for structural changes
2. Edit `~/.config/ags/style.css` for visual changes
3. Regenerate and restart AGS shell

Or just ask Claude Code: `costa-ai "add a CPU temperature module to the shell bar"`.

### Adding Keybinds

There are three ways to add or modify keybinds:

**1. Graphical Keybind Configurator**

Click the 󰌌 icon in the shell bar, or run `costa-keybinds-gui`. This opens a GTK4 application with two tabs:

- **Keyboard**: All keybinds grouped by category (Applications, Window Management, Workspaces, Media, etc.), searchable, with edit/add/delete buttons
- **Mouse**: Auto-discovers connected mice, shows button codes, includes a "Press to Detect" feature for identifying buttons

To add a new keybind: click the + button, record your key combination (or type it manually if Hyprland intercepts the recording), select the action, and save.

**2. CLI tool**

```bash
costa-keybinds list                              # show all keybinds
costa-keybinds list --filter volume              # filter by keyword
costa-keybinds add "SUPER" "F1" "exec" "firefox"  # add a new keybind
costa-keybinds remove "SUPER" "F1"               # remove a keybind
costa-keybinds mouse                             # show mouse button mappings
costa-keybinds mouse detect                      # identify a button by pressing it
```

**3. Manual editing**

Edit `~/.config/hypr/hyprland.conf` directly:

```ini
bind = SUPER, F5, exec, costa-ai "what time is it"
bind = SUPER SHIFT, G, exec, gimp
binde = , XF86AudioRaiseVolume, exec, wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+
```

After editing, reload with `hyprctl reload`.

**Bind types:**

| Type | Behavior |
|------|----------|
| `bind` | Triggers once on keypress |
| `binde` | Repeats while held (volume, resize) |
| `bindm` | Mouse bind (drag operations) |
| `bindl` | Works even when screen is locked |
| `bindr` | Triggers on key release |

### Window Rules

See the [Window Rules section in Desktop Management](#window-rules) above for details. Quick reference:

```ini
# Common window rule examples
windowrule = float, class:^(pavucontrol)$           # audio mixer always floats
windowrule = workspace 5, class:^(Spotify)$          # Spotify always on workspace 5
windowrule = opacity 0.95, class:^(ghostty)$         # slightly transparent terminal
windowrule = size 800 600, class:^(calculator)$       # fixed size for calculator
windowrule = center, class:^(com.costa.settings)$    # center the settings hub
windowrule = pin, class:^(rofi)$                      # rofi stays on top
```

Find app class names with `hyprctl clients -j | jq '.[].class'`.

### Changing Default Applications

Edit the variables at the top of `~/.config/hypr/hyprland.conf`:

```ini
$terminal = ghostty
$fileManager = thunar
$menu = rofi -show drun
$browser = firefox
```

Then reload: `hyprctl reload`.

To change the default application for opening files (what `xdg-open` uses):

```bash
# Set default browser
xdg-settings set default-web-browser firefox.desktop

# Set default file manager
xdg-mime default thunar.desktop inode/directory

# Set default text editor
xdg-mime default code.desktop text/plain
```

---

## 7. Music and Media

### The Music Widget

Costa OS includes a custom floating music widget that controls any MPRIS-compatible player (Strawberry, Spotify, Firefox, VLC, and more).

**Opening the widget:**

- Click the music icon (󰎆) or the now-playing text in the shell bar
- Or run: `costa-music-widget`

The widget shows album art, track information, a progress bar with seek controls, playback buttons, and a quality badge showing the live audio format from PipeWire (for example, "24bit / 96kHz", highlighted in teal when the format is hi-res).

<!-- screenshot: The Costa music widget showing album art on the left, track name and artist, a progress bar, playback controls, and the audio quality badge reading "24bit / 48kHz". -->

The widget has a tabbed interface:

| Tab | Content |
|-----|---------|
| **Now Playing** | Album art, controls, progress, quality badge |
| **Queue** | Current playlist with track list: click to jump, drag to reorder |
| **Search** | Search your Strawberry music library by title, artist, or album |
| **Playlists** | Switch between playlists without opening Strawberry |

### Player Controls and Keybinds

**Global keyboard shortcuts** (work regardless of focused window):

| Keybind | Action |
|---------|--------|
| `SUPER+]` | Next track |
| `SUPER+[` | Previous track |
| `SUPER+\` | Play/pause |
| Media Play/Pause key | Play/pause |
| Media Next/Prev keys | Next/previous track |

**Shell bar now-playing controls:**

| Mouse Action | What It Does |
|-------------|-------------|
| Left-click | Open the music widget |
| Middle-click | Play/pause |
| Right-click | Next track |
| Scroll up | Seek forward 5 seconds |
| Scroll down | Seek backward 5 seconds |

**CLI controls** (useful in scripts or for voice commands):

```bash
playerctl play-pause            # toggle playback
playerctl next                  # next track
playerctl previous              # previous track
playerctl position 10+          # seek forward 10 seconds
playerctl position 10-          # seek backward 10 seconds
playerctl position 30           # jump to 30 seconds in
playerctl shuffle toggle        # toggle shuffle
playerctl loop Track            # repeat current track
playerctl loop Playlist         # repeat playlist
playerctl loop None             # disable repeat
```

### Cold Starting Music

If no music player is running, you can start playback from the widget:

1. Open the music widget (click 󰎆 in the shell bar)
2. Click "Start Music"
3. This launches Strawberry in the background and begins playback
4. The Strawberry window stays hidden on a special workspace, the widget controls it

If Strawberry has no music library configured, it opens the library setup dialog so you can point it at your music folder (typically `~/Music/`).

### Switching Players

The music widget supports any MPRIS-compatible player. A dropdown in the widget header shows the active player. Click it to switch between:

- **Strawberry**: local music library
- **Spotify**: streaming (via spotify-launcher)
- **Firefox**: browser audio/video
- Any other MPRIS player

From the CLI:

```bash
playerctl --list-all                    # list all active players
playerctl -p strawberry play-pause      # control a specific player
playerctl -p spotify next               # next track on Spotify
```

### Library Search and Playlists

The Search tab in the music widget queries Strawberry's SQLite database directly, you do not need to open Strawberry's GUI. Type to search across artist, album, and track name. Click a result to play it, or right-click to add it to the queue.

The Playlists tab shows all playlists from Strawberry. Click a playlist name to load and play it. To create new playlists, use Strawberry directly: right-click in the playlist area and select "New Playlist."

### Volume and Audio Output

**Volume control:**

```bash
wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.5       # set to 50%
wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+        # increase by 5%
wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-        # decrease by 5%
wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle       # mute/unmute speakers
wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle     # mute/unmute microphone
```

**Switching audio output** (for example, from speakers to headphones):

```bash
pactl list sinks short                           # list available outputs
pactl set-default-sink SINK_NAME                 # switch to a specific output
```

For visual audio routing, use `qpwgraph` (GUI graph editor) or `pavucontrol` (traditional mixer).

---

## 8. System Administration

### Installing Packages

Costa OS uses Arch Linux's `pacman` package manager for official repositories and `yay` for the AUR (Arch User Repository, which contains community-maintained packages).

**The easiest way:** just ask the AI.

```bash
costa-ai "install Blender"
```

The AI will determine whether the package is in the official repos or AUR, show you the install command, and ask for confirmation before running it.

**Manual installation:**

```bash
# Official repositories
sudo pacman -S blender

# AUR (community packages)
yay -S spotify-launcher

# Search for a package
pacman -Ss keyword                # search official repos
yay -Ss keyword                   # search official + AUR

# Get info about a package
pacman -Qi package                # info for an installed package
pacman -Si package                # info for a remote package

# Remove a package (with dependencies and configs)
sudo pacman -Rns package
```

### System Updates

Costa OS is a rolling-release distribution, meaning you get the latest versions of everything through regular updates rather than major version upgrades.

**Through the Settings Hub:**

1. Open Settings Hub (`SUPER+I`)
2. Go to System and click "Check for Updates"
3. Review the list of updates and click Apply

**Through the terminal:**

```bash
# Update everything (official repos + AUR)
yay -Syu

# Update official repos only
sudo pacman -Syu
```

**Maintenance tasks:**

```bash
# Remove orphan packages (installed as dependencies, no longer needed)
sudo pacman -Rns $(pacman -Qtdq)

# Clear package cache (keep last 2 versions)
paccache -rk2

# Check which package owns a file
pacman -Qo /path/to/file

# Downgrade a package
sudo pacman -U /var/cache/pacman/pkg/package-version.pkg.tar.zst
```

Or use the built-in `cleanup` workflow: `costa-flow run cleanup`.

### Managing Services

Costa OS uses systemd for service management, like all modern Linux distributions.

```bash
# Check service status
systemctl status ollama
systemctl --user status costa-clipboard    # user-level service

# Start, stop, restart
sudo systemctl start ollama
sudo systemctl stop ollama
sudo systemctl restart ollama

# Enable/disable auto-start on boot
sudo systemctl enable ollama
sudo systemctl disable ollama

# List running services
systemctl list-units --state=running

# List failed services
systemctl --failed

# View service logs
journalctl -u ollama -f                    # follow live logs
journalctl -u ollama -n 50                 # last 50 lines
```

User-level services (like the clipboard daemon) use `systemctl --user` instead of `sudo systemctl`.

### Audio Configuration (PipeWire)

Costa OS uses PipeWire with WirePlumber for all audio. PipeWire is a modern audio system that replaces PulseAudio and JACK while maintaining compatibility with both.

**Common commands:**

```bash
# Check audio status
wpctl status                              # full audio graph
pw-top                                    # real-time audio activity

# Volume control
wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.7  # set to 70%
wpctl get-volume @DEFAULT_AUDIO_SINK@      # check current volume

# Device management
pactl list sources short                   # list microphones
pactl list sinks short                     # list speakers/outputs
pactl set-default-source "device_name"     # set default microphone
pactl set-default-sink "device_name"       # set default speakers

# Visual audio routing
qpwgraph                                  # GUI graph editor
```

**Troubleshooting audio:**

| Problem | Solution |
|---------|----------|
| No sound | Check `wpctl status`, verify the correct sink is set as default |
| Wrong device | `pactl set-default-sink "device_name"` |
| Crackling/popping | Increase quantum: edit `~/.config/pipewire/pipewire.conf` and set `default.clock.quantum = 512` |
| App audio not showing | Restart PipeWire: `systemctl --user restart pipewire` |

**Restarting the entire audio stack:**

```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
```

### Network and WiFi

Costa OS uses NetworkManager for network management.

**WiFi:**

```bash
# List available networks
nmcli device wifi list

# Connect to a network
nmcli device wifi connect "MyNetwork" password "MyPassword"

# Disconnect
nmcli connection down "MyNetwork"

# Show saved connections
nmcli connection show

# Interactive TUI
nmtui
```

**Wired/Ethernet:**

```bash
nmcli device status                        # show all interfaces
nmcli device connect eth0                  # connect wired
```

**Diagnostics:**

```bash
ip addr                                    # show IP addresses
ip route | grep default                    # show default gateway
ping -c4 archlinux.org                     # test connectivity
ss -tlnp                                   # show listening ports
curl -s ifconfig.me                        # show public IP
bandwhich                                  # live bandwidth monitor (needs sudo)
dog google.com                             # DNS lookup
```

**VPN:**

```bash
# WireGuard
sudo wg-quick up wg0
sudo wg-quick down wg0

# OpenVPN
sudo openvpn --config file.ovpn

# Import WireGuard config into NetworkManager
nmcli connection import type wireguard file wg0.conf
```

### Bluetooth

```bash
# Power on and scan
bluetoothctl power on
bluetoothctl scan on                       # Ctrl+C to stop scanning

# Pair and connect a device
bluetoothctl pair XX:XX:XX:XX:XX:XX
bluetoothctl trust XX:XX:XX:XX:XX:XX       # auto-reconnect in future
bluetoothctl connect XX:XX:XX:XX:XX:XX

# Disconnect and remove
bluetoothctl disconnect XX:XX:XX:XX:XX:XX
bluetoothctl remove XX:XX:XX:XX:XX:XX      # forget device

# List paired devices
bluetoothctl paired-devices
```

**After connecting Bluetooth audio:**

```bash
# Find the Bluetooth sink
pactl list sinks short

# Switch audio to it
pactl set-default-sink bluez_output.XX_XX_XX_XX_XX_XX.1
```

**Game controllers:** Most controllers work automatically after pairing. For PS5 DualSense, hold Share + PS button until the light flashes fast. For Xbox, hold the sync button.

### USB Drives and External Storage

USB drives typically auto-mount via udisks2. When you plug in a drive, it appears in Thunar's sidebar and at `/run/media/$USER/DRIVELABEL`.

```bash
# List all drives
lsblk
lsblk -f                                  # show filesystem, labels, UUIDs

# Mount manually (if auto-mount doesn't work)
udisksctl mount -b /dev/sdb1

# Safe eject
udisksctl unmount -b /dev/sdb1
udisksctl power-off -b /dev/sdb

# If the drive is busy
sudo umount -l /dev/sdb1                   # lazy unmount
sudo lsof /run/media/$USER/DRIVELABEL      # find what's using it
```

**Formatting** (only when you explicitly want to erase the drive):

```bash
sudo mkfs.ext4 /dev/sdb1                  # Linux format
sudo mkfs.fat -F32 /dev/sdb1              # FAT32 (universal compatibility)
sudo mkfs.ntfs /dev/sdb1                  # NTFS (Windows compatibility)
```

**Flashing an ISO to USB:**

```bash
sudo dd if=costa-os.iso of=/dev/sdb bs=4M status=progress conv=fsync
```

This erases the entire drive. Use the whole device (`/dev/sdb`), not a partition (`/dev/sdb1`).

### Display and Brightness

**Brightness** (laptops):

```bash
brightnessctl set 50%                      # set to 50%
brightnessctl set +10%                     # increase by 10%
brightnessctl set 10%-                     # decrease by 10%
```

**Night light / blue light filter:**

```bash
gammastep -O 4500                          # set warm color temperature (Kelvin)
gammastep -l 42.3:-71.0                    # auto day/night based on location
killall gammastep                          # reset to normal
```

**Monitor management:**

```bash
hyprctl monitors                           # list monitors
hyprctl keyword monitor DP-1,2560x1440@165,auto,1    # change resolution/refresh
hyprctl keyword monitor HDMI-A-2,disable              # disable a monitor
```

### Notifications

Costa OS uses Dunst for notifications. Notifications from the AI, clipboard intelligence, screenshots, and regular applications all appear through Dunst.

```bash
# Send a test notification
notify-send "Hello" "This is a test notification"

# Dismiss current notification
dunstctl close

# Dismiss all notifications
dunstctl close-all

# Show notification history
dunstctl history-pop

# Toggle Do Not Disturb
dunstctl set-paused toggle
```

Configuration: `~/.config/dunst/dunstrc`. Restart after changes: `killall dunst; dunst &disown`.

---

## 9. Advanced Features

### VRAM Manager

The VRAM manager is a background daemon that automatically keeps the best AI model loaded in your GPU memory. You never need to think about model management, it handles everything.

**How it works:**

1. Checks total GPU VRAM (for example, 16GB on an RX 9060 XT)
2. Subtracts VRAM used by other applications (games, browsers, video editors)
3. Subtracts a 2GB headroom buffer to prevent memory thrashing
4. Loads the largest model that fits in the remaining space

**Model tiers:**

| Available VRAM | Model | Quality |
|---------------|-------|---------|
| 12GB+ | qwen2.5:14b (~11GB) | Best local intelligence |
| 6--12GB | qwen2.5:7b (~6.5GB) | Good quality |
| 3--6GB | qwen2.5:3b (~4GB) | Fast, basic answers |
| <3GB | None loaded (gaming mode) | All queries go to cloud |

**Gaming mode:** When you launch a game and it claims VRAM, models automatically unload. All AI queries route to cloud (Claude Haiku/Sonnet). When the game exits, the best-fit model reloads within seconds.

**Checking current state:**

```bash
cat $XDG_RUNTIME_DIR/costa/ollama-smart-model                # currently loaded model name
cat /tmp/ollama-tier                       # current tier (full/medium/reduced/gaming)
ollama ps                                  # show loaded models and VRAM usage
```

The VRAM manager script lives at `~/.config/hypr/ollama-manager.sh` and runs as a background process started by Hyprland.

### Workflows (costa-flow)

Workflows are automated multi-step tasks defined in YAML. They can run shell commands, ask the AI, branch on conditions, and be scheduled on timers.

**Running workflows:**

```bash
costa-flow list                            # list all available workflows
costa-flow run system-health               # run a specific workflow
costa-flow run morning-briefing            # another example
costa-flow status                          # check running/recent workflows
```

**Built-in workflows:**

| Workflow | What It Does |
|----------|-------------|
| `system-health` | Check disk, memory, failed services, journal errors |
| `smart-update` | Update packages, rebuild AUR, check for issues |
| `backup-check` | Verify chezmoi state, check commits, diff dotfiles |
| `cleanup` | Remove orphans, clear caches, prune Docker |
| `docker-watch` | Check container health, restart unhealthy ones |
| `morning-briefing` | Weather, calendar, system status, notifications |
| `security-scan` | Check failed logins, open ports, outdated packages |
| `log-digest` | AI-summarize recent journal errors and warnings |
| `ollama-model-update` | Check for and pull updated model versions |
| `project-standup` | Git status across all projects, uncommitted changes, PR status |

**Creating a custom workflow:**

Create a YAML file in `~/.config/costa/workflows/`:

```yaml
name: my-workflow
description: Check Docker containers and summarize
schedule: "0 9 * * *"          # optional: run daily at 9am

steps:
  - id: containers
    type: shell
    command: docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

  - id: analyze
    type: ai
    prompt: "Summarize the status of these Docker containers"
    input_from: [containers]

  - id: alert
    type: condition
    if: "{{ analyze.contains('unhealthy') }}"
    then:
      type: shell
      command: notify-send "Docker Alert" "{{ analyze.output }}"
```

**Step types:**

- `shell`: run a command, capture output
- `ai`: send a prompt to costa-ai (can include output from previous steps via `input_from`)
- `condition`: branch based on previous step output

**Scheduling:**

Workflows with a `schedule:` field use cron syntax:

```bash
costa-flow enable my-workflow              # activate the schedule
costa-flow disable my-workflow             # deactivate
costa-flow schedule                        # list all scheduled workflows
```

### Project Management

Costa OS can switch your entire workspace context, open the right editor, terminal, browser, and services, with a single command.

**Switching projects:**

```bash
costa-ai "switch to my-webapp"               # by name
costa-ai "switch to para"                   # fuzzy matching works
```

Or by voice: hold `SUPER+ALT+V` and say "switch to my-webapp."

Or through the shell bar: click the folder icon to open the project list, or scroll on it to cycle through recent projects.

**What happens when you switch:**

1. Hyprland switches to the project's configured workspace
2. Apps launch in configured positions (editor on the left, terminal on the right, etc.)
3. Environment variables are set
4. Setup commands run (for example, `docker compose up -d`)

**Creating a project config:**

Create a YAML file in `~/.config/costa/projects/`:

```yaml
name: my-webapp
directory: ~/projects/my-webapp
workspace: 2

apps:
  - command: code ~/projects/my-webapp
    position: left
  - command: ghostty -e "cd ~/projects/my-webapp && zsh"
    position: right
  - command: firefox --new-window "http://localhost:3000"
    position: floating

env:
  DATABASE_URL: "postgresql://localhost/my-webapp"
  NODE_ENV: "development"

setup:
  - docker compose up -d
  - npm run dev &disown
```

Or ask the AI to create one: `costa-ai "create a project config for ~/projects/myapp with VS Code and a terminal"`.

### AI Agents

Agents are specialized AI personas with focused expertise, specific tool access, and assigned models. Instead of asking the general AI everything, agents know their domain deeply.

**Available agents:**

| Agent | Model | Purpose |
|-------|-------|---------|
| **sysadmin** | qwen2.5:14b (local) | System health, packages, services, disk, logs |
| **architect** | Claude Sonnet (cloud) | System design, code review, architecture decisions |
| **builder** | Claude Sonnet (cloud) | Write code, implement features, fix bugs |
| **deployer** | qwen2.5:14b (local) | Docker, CI/CD, server config, deployments |
| **janitor** | qwen2.5:3b (local) | Clean caches, remove orphan packages, free disk |
| **monitor** | qwen2.5:3b (local) | Watch logs, alert on errors, track resources |

**Using agents:**

```bash
costa-agents run sysadmin "check disk usage"
costa-agents run janitor "clean up old docker images"
costa-agents run architect "review the database schema in ~/projects/myapp"

# Or via the preset flag
costa-ai --preset sysadmin "why is my CPU usage high"
```

**By voice:** Say the agent name in your command: "Hey Costa, sysadmin check what's using all my RAM."

**Creating custom agents:**

Create a YAML file in `~/.config/costa/agents/`:

```yaml
name: database
description: "Database administration and query optimization"
model: qwen2.5:14b
system_prompt: |
  You are a database administrator for PostgreSQL and SQLite.
  You help with query optimization, schema design, migrations,
  and troubleshooting connection issues.
tools:
  - read_file
  - execute_sql_readonly
  - list_tables
constraints:
  - never_execute_destructive_sql
  - require_confirmation_for_schema_changes
```

**Queue management:**

```bash
costa-agents list                          # show all agents
costa-agents queue                         # show running and queued tasks
costa-agents cancel <task-id>              # cancel a queued task
costa-agents log deployer                  # view agent logs
```

Local agent tasks run in unlimited parallel. Cloud agent tasks queue serially to manage API rate limits and costs.

### Clipboard Intelligence

Clipboard Intelligence is a background daemon that watches what you copy, classifies the content, and shows a notification with contextual actions.

**Content types detected:**

| Type | Actions Offered |
|------|----------------|
| Error / stack trace | "Ask AI to Debug", "Search Web", "Copy Clean" |
| URL | "Open in Browser", "Open in Background", "Preview" |
| JSON | "Pretty Print", "Validate", "Extract Keys" |
| Shell command | "Run", "Run Silent", "Edit First" |
| Code snippet | "Explain", "Save to File", "Format" |
| File path | "Open File", "Open Directory", "Copy Contents" |

**How it works:**

1. The `costa-clipboard-daemon` monitors your clipboard via `wl-paste --watch`
2. Each new entry is classified using pattern matching and optionally the local AI
3. A Dunst notification appears with detected type and action buttons
4. Click an action to execute it
5. All entries are stored in `cliphist` for history

**Clipboard history:**

Press `SUPER+V` to open clipboard history in Rofi. Type to filter. Press Enter to paste.

```bash
cliphist wipe                              # clear clipboard history
```

**Service management:**

```bash
systemctl --user status costa-clipboard     # check if running
systemctl --user restart costa-clipboard    # restart
systemctl --user disable --now costa-clipboard   # disable
systemctl --user enable --now costa-clipboard    # re-enable
```

**Configuration** (`~/.config/costa/clipboard.yaml`):

```yaml
enabled: true
classify_with_ai: true             # use local LLM for ambiguous content
notification_timeout: 8            # seconds before auto-dismiss
dangerous_command_confirm: true    # always confirm destructive commands
ignored_apps: []                   # app classes to ignore
max_history: 1000                  # max entries in cliphist
```

### Screenshot AI

Costa OS integrates AI analysis directly into the screenshot workflow.

**Screenshot keybinds:**

| Keybind | Action |
|---------|--------|
| `Print` | Screenshot region, save to `~/Pictures/Screenshots/` |
| `SUPER+Print` | Screenshot region, copy to clipboard |
| `SUPER+SHIFT+Print` | Screenshot full screen |
| `SUPER+SHIFT+A` | AI screenshot: select region, get AI analysis |
| `SUPER+SHIFT+T` | OCR screenshot: select region, extract text to clipboard |

**AI screenshot analysis:**

1. Press `SUPER+SHIFT+A`
2. Select a region with your mouse
3. The screenshot is sent to Claude Haiku for analysis
4. A notification shows the AI's interpretation
5. The full response is copied to your clipboard

This is especially useful for error messages. When the AI detects an error in the screenshot, it classifies the type (compiler error, runtime exception, config issue) and suggests a fix. Click "Apply Fix" if the suggestion involves a command, or "Explain More" for a detailed breakdown.

**OCR text extraction:**

1. Press `SUPER+SHIFT+T`
2. Select a region containing text
3. Text is extracted via Tesseract OCR, copied to clipboard, and saved to `/tmp/costa-ocr-latest.txt`

**Screen recording:**

```bash
wf-recorder -o DP-1 -f recording.mp4       # record a monitor
wf-recorder -g "$(slurp)" -f recording.mp4  # record a selected region
wf-recorder -a -f recording.mp4             # record with audio
killall wf-recorder                         # stop recording
```

**Color picker:**

```bash
hyprpicker -a                               # click anywhere to copy hex color to clipboard
```

### Face Authentication

Costa OS supports Windows Hello-style face unlock using Howdy, a Linux face recognition system that works through your IR (infrared) camera.

**Requirements:** An IR camera, typically found in laptops with Windows Hello support. Costa OS auto-detects IR cameras during first boot. If none is found, face auth setup is skipped entirely. Regular webcams technically work but are much less secure (easier to spoof with photos).

**Setting up face auth:**

1. Open Settings Hub (`SUPER+I`) and go to Security > Face Authentication > "Enroll Face"
2. Position your face in front of the IR camera and hold still for 2--3 seconds
3. Repeat the enrollment 3--5 times at different angles (straight on, slight left, slight right, with/without glasses) for reliable recognition

Or from the terminal:

```bash
sudo howdy add                             # enroll (repeat 3-5 times)
sudo howdy test                            # test recognition
sudo howdy list                            # list enrolled face models
sudo howdy remove <id>                     # remove a specific model
sudo howdy clear                           # remove all models
```

**Where face auth works:**

| Context | Behavior |
|---------|----------|
| Login (greetd) | Look at camera to log in automatically |
| Sudo commands | Face auth tries first, then falls back to password |
| Screen lock (hyprlock) | Look at camera to unlock |

**Password always works as fallback.** Face auth is configured as "sufficient" in PAM, not "required." If recognition fails for any reason, the password prompt appears normally.

### Touchscreen Support

Costa OS auto-detects touchscreens and configures three components:

- **squeekboard**: on-screen keyboard that appears automatically in text fields
- **hyprgrass**: Hyprland plugin for multi-touch gestures
- **libinput**: kernel-level touch input

If no touchscreen is detected, these components are not installed.

**Touch gestures:**

| Gesture | Fingers | Action |
|---------|---------|--------|
| Swipe up | 3 | Open app launcher (Rofi) |
| Swipe down | 3 | Close focused window |
| Swipe left | 3 | Next workspace |
| Swipe right | 3 | Previous workspace |
| Swipe up | 4 | Toggle fullscreen |
| Swipe down | 4 | Toggle floating |
| Long press | 2 | Move window (drag after press) |

**Toggle touchscreen:**

- Settings Hub > Input > Touchscreen > toggle on/off
- Or: `hyprctl keyword input:touchdevice:enabled false`

Configuration: `~/.config/hypr/touch.conf`

### Settings Hub

The Settings Hub is a central GTK4 application for configuring Costa OS. It covers display, security, input, AI, development, and system settings.

**How to open:**

- Click the gear icon (󰒓) in the shell bar
- Press `SUPER+I`
- Run `costa-settings` from a terminal
- Say "open settings" to the voice assistant

**Sections:**

| Section | What You Can Configure |
|---------|----------------------|
| **Display** | Monitor layout, shell bar regeneration, wallpaper picker |
| **Security** | Face authentication enrollment and testing |
| **Input** | Touchscreen toggle, keybinds GUI launcher |
| **AI Assistant** | Ollama model management, API key entry, voice status, tier selection |
| **Development** | GitHub CLI authentication, SSH key generation |
| **System** | Package updates, dotfiles sync (chezmoi), re-run first boot |

Each section shows a status indicator:
- Green checkmark, fully configured
- Yellow warning, partially configured or optional step skipped
- Red X, required setup not completed
- Gray circle, not applicable (for example, touchscreen on a desktop)

### AI Navigation (costa-nav)

costa-nav is a proprietary MCP navigation system under development that lets Claude Code interact with graphical applications without taking screenshots. This is 112x cheaper in tokens than screenshot-based approaches.

**How it works:**

1. Claude sends a plan (for example, "check credit balance, if under $10, find the warning")
2. costa-nav reads the application's screen content (free, instant, no screenshots)
3. The local Ollama model interprets the content (~3 seconds)
4. Actions execute mechanically (clicks, typing, scrolling)
5. Claude gets back 50--80 tokens of structured answers

**Levels:**

| Level | Command | Purpose |
|-------|---------|---------|
| 0 | `costa-nav read <app>` | Raw accessibility dump (debugging) |
| 1 | `costa-nav query '{json}'` | Batch questions answered by local model |
| 2 | `costa-nav plan '{json}'` | Conditional plans with actions |
| 3 | `costa-nav routine <name>` | Saved plans triggered by name |

**Claude's virtual monitor:** Claude operates on an invisible headless display (HEADLESS-2, workspace 7). It can open its own browser, navigate pages, and interact with GUIs without touching your screen. Toggle a live preview by clicking the 󰍹 icon in the shell bar.

**Self-learning:** The system accumulates site-specific knowledge as it runs, stored in `~/.config/costa/nav-sites/`. Element locations, page behavior, and what worked are remembered for future use.

### Document RAG

You can index your own documents so the AI can search and reference them when answering questions:

```bash
costa-ai --index ~/projects/myapp/docs     # index a directory
costa-ai --index ~/notes                   # index personal notes
```

Indexed content uses SQLite FTS5 full-text search with relevance ranking. When you ask a question that matches indexed content, the relevant text is automatically injected as context.

---

## 10. Troubleshooting

### Common Issues and Fixes

**Hyprland config errors:**

```bash
hyprctl configerrors                       # show config errors
hyprctl reload                             # reload after fixing
```

**GPU not detected or issues:**

```bash
source ~/.config/costa/gpu.conf && echo $GPU_NAME   # check detected GPU
lspci | grep VGA                                      # raw PCI device info
```

**Audio issues:**

```bash
wpctl status                               # check audio graph
pactl list sinks short                     # list outputs
pactl list sources short                   # list inputs
systemctl --user restart pipewire pipewire-pulse wireplumber   # restart audio stack
```

**Ollama not responding:**

```bash
systemctl status ollama                    # check service status
systemctl restart ollama                   # restart
ollama ps                                  # check loaded models
cat $XDG_RUNTIME_DIR/costa/ollama-smart-model                # check VRAM manager's model selection
```

**Application will not close:**

```bash
hyprctl dispatch killactive                # close focused window via Hyprland
# If that doesn't work:
hyprctl dispatch closewindow class:appname  # close by class name
kill PID                                    # kill by process ID
pkill -f processname                       # kill by name
```

**Electron apps (VS Code, Discord, etc.) have issues:**

Some Electron apps need flags for Wayland:
- `--ozone-platform=wayland` (native Wayland)
- `--ozone-platform=x11` (XWayland, needed for global keybinds in some apps)

Vesktop (Discord) specifically needs `--ozone-platform=x11` for global push-to-talk to work.

**Window is stuck or hidden:**

```bash
hyprctl clients -j | jq '.[] | {class, title, workspace}'   # find all windows
hyprctl dispatch movetoworkspace 1,class:appname              # move to visible workspace
```

### Where to Find Logs

| Log Type | Command |
|----------|---------|
| System logs (current boot) | `journalctl -b` |
| System errors only | `journalctl -b -p err` |
| Specific service | `journalctl -u ollama -f` |
| User service | `journalctl --user -u costa-clipboard -f` |
| Kernel messages | `dmesg --level=err,warn` |
| Previous boot | `journalctl -b -1` |
| Hyprland errors | `hyprctl configerrors` |
| PTT voice status | `cat /tmp/ptt-voice-status` |
| AI last output | `cat /tmp/ptt-voice-output` |

### How to Reset Configs

**Reset a specific component:**

```bash
# Reset Hyprland to default
cp /usr/share/costa/configs/hyprland.conf ~/.config/hypr/hyprland.conf
hyprctl reload

# Reset AGS shell
~/.config/costa/scripts/generate-ags-config.sh
ags quit; ags run &disown

# Reset Dunst
cp /usr/share/costa/configs/dunstrc ~/.config/dunst/dunstrc
killall dunst; dunst &disown
```

**Re-run the entire first-boot setup:**

```bash
costa-firstboot --reconfigure
```

Or through the Settings Hub: System > "Re-run First Boot." This is safe to run, it skips steps already completed and re-detects hardware.

**Nuclear option (reset all Costa configs):**

```bash
rm -rf ~/.config/costa/
costa-firstboot --reconfigure
```

This deletes your AI history, knowledge patches, workflow configs, and project configs. Use this only as a last resort.

### Getting Help

**Ask the AI:**

The AI assistant is the fastest way to get help. It has access to your system state and all the knowledge files:

```bash
costa-ai "why is my fan running so loud"
costa-ai "how do I connect to WiFi"
costa-ai "my audio is crackling, how do I fix it"
```

**Voice:**

Hold `SUPER+ALT+V` and describe your problem.

**Costa OS resources:**

- GitHub repository: [github.com/superninjv/costa-os](https://github.com/superninjv/costa-os)
- File issues on GitHub for bugs or feature requests

**Upstream resources:**

- [Arch Wiki](https://wiki.archlinux.org/), the definitive resource for Arch Linux
- [Hyprland Wiki](https://wiki.hyprland.org/). Hyprland configuration reference
- [PipeWire Wiki](https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/home), audio system documentation

---

## 11. Privacy and Security

### Data Collection Policy

**Costa OS collects nothing.** No analytics, no telemetry, no crash reports, no usage data. There are no accounts, no registration, and no Costa OS servers. The OS never phones home. Period.

The entire codebase is open source under the Apache License 2.0, so you can verify this yourself.

### Where Your Data Lives

All data Costa OS generates stays on your local machine:

| Data | Location | Details |
|------|----------|---------|
| AI conversation history | `~/.config/costa/costa.db` | SQLite database, local only |
| API keys | `~/.config/costa/env` | Stored with `chmod 600` (owner-read only) |
| Voice recordings | `/tmp/` (temporary) | Processed locally by Whisper, deleted immediately after transcription |
| Face authentication | Local howdy data | Stored on-device, never transmitted |
| Configuration | `~/.config/costa/` and `~/.config/hypr/` | Standard config files on your filesystem |
| Clipboard history | `cliphist` database | Local, managed by cliphist |
| Knowledge corrections | `~/.config/costa/knowledge/.corrections.json` | Local patches from feedback reports |
| Navigation site data | `~/.config/costa/nav-sites/` | Learned site patterns, local only |

You can delete any of this data at any time. `rm -rf ~/.config/costa/` removes everything Costa-specific. It is your machine.

### API Key Management

If you choose to use cloud AI (Claude by Anthropic or OpenAI), your API keys are:

- Stored locally in `~/.config/costa/env` with restrictive file permissions (`chmod 600`, only your user can read them)
- Sent directly from your machine to the provider's API (`api.anthropic.com` or `api.openai.com`)
- Never proxied through any Costa OS server (there are no Costa OS servers)
- Never logged, transmitted, or shared with anyone other than the configured provider

**Setting API keys:**

1. Settings Hub > AI Assistant > API Keys
2. Or edit `~/.config/costa/env` manually:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   OPENAI_API_KEY=sk-...
   ```
3. Reload: `source ~/.config/costa/env`

Costa OS also works with Claude Pro/Max subscription tokens, no separate API billing required if you already have a Claude plan.

### Face Auth Security

Howdy (the face authentication system) is a **convenience feature, not a security-grade biometric system.** Important things to understand:

- It can be fooled by photos in some conditions, especially with regular webcams
- IR cameras are significantly harder to spoof (infrared does not reflect from printed photos the same way as real faces)
- Face auth is configured as "sufficient" in PAM, meaning your password is always the security baseline
- Never rely solely on face auth for sensitive operations
- Face data is stored entirely on your local machine and never transmitted

You can disable face auth at any time through the Settings Hub or by removing the howdy lines from PAM configuration files (`/etc/pam.d/sudo`, `/etc/pam.d/greetd`, `/etc/pam.d/hyprlock`).

### Voice Assistant Privacy

The voice assistant is designed with privacy as a core principle:

1. **Recording**: Audio is captured only while you hold the push-to-talk key. There is no always-on listening.
2. **Processing**: The recording is processed locally by DeepFilterNet (noise reduction) and Whisper (speech-to-text) on your own hardware.
3. **Deletion**: The audio file is deleted immediately after transcription. It is never uploaded anywhere.
4. **Transcription**: The text goes to your local Ollama model. If cloud escalation is triggered, only the text (never the audio) is sent to the cloud provider.

No voice data is ever stored permanently, uploaded, or used for training.

### Network Connections Costa OS Makes

Costa OS makes network connections only for user-initiated or standard system operations:

| Connection | Destination | Purpose | When |
|------------|-------------|---------|------|
| Package updates | Arch Linux repos | System and software updates | When you run `pacman -Syu` or `yay` |
| Weather data | `wttr.in` | Weather queries | When you ask about the weather |
| Model downloads | `ollama.com` | Downloading AI models | When you pull a new Ollama model |
| Cloud AI (optional) | `api.anthropic.com` / `api.openai.com` | Queries beyond local capability | Only if you configure API keys |
| AUR packages | `aur.archlinux.org` | Community package builds | When you install AUR packages |

That is the complete list. There is no background telemetry, no analytics beacon, no heartbeat ping, and no update check phoning home to Costa OS servers. There are no Costa OS servers.

---

## 12. Contributing

### How to Contribute

Costa OS is open source under the Apache License 2.0. The repository is at [github.com/superninjv/costa-os](https://github.com/superninjv/costa-os).

Development is managed by the Costa OS team. External contributions are not accepted via pull requests at this time. However, there are ways to help:

- **Report bugs**: File an issue on GitHub with steps to reproduce, expected behavior, and actual behavior
- **Suggest features**: Open a feature request issue describing what you want and why
- **Test on hardware**: Report compatibility results for different GPUs, monitors, and peripherals in a GitHub issue

The codebase is open source so you can read, fork, and learn from it, but the canonical repository is maintained exclusively by the team.

### Project Structure

```
costa-os/
  ai-router/          Core intelligence layer (context gathering, model routing,
                       auto-escalation, tools, workflows, ML router, RAG, queue)
  packages/           Package lists by category (base, dev, creative, gaming)
  configs/            Default config templates with Costa theme applied
  voice-assistant/    Push-to-talk voice assistant source
  scripts/            Automation and utility scripts
  branding/           Logo, wallpapers, boot splash images
  docs/               User guide, architecture docs, privacy policy
  knowledge/          Knowledge base files (shipped with the OS, injected into local LLM)
  mcp-server/         Claude Code MCP server (system tools, screen reading)
```

### Getting the Source

The Costa OS intelligence layer is open source:

```bash
git clone https://github.com/superninjv/costa-os.git
```

This gives you the AI router, knowledge base, MCP server, configs, and voice assistant source. You can use these components on any existing Arch Linux + Hyprland setup.

The installer and ISO are distributed as a download from [synoros.io/costa-os](https://synoros.io/costa-os).

### Filing Issues

When filing an issue on GitHub, include:

1. **What you expected to happen** and **what actually happened**
2. **Steps to reproduce** the issue
3. **System information**: GPU model, monitor setup, relevant package versions
4. **Logs**: output from `journalctl`, `hyprctl configerrors`, or relevant service logs
5. **Configuration**: relevant snippets from config files (redact any API keys)

For AI-related issues, also include:
- The query you sent
- The model that handled it (check `costa-ai --history`)
- The response you received
- What the correct response should have been

---

*This guide was written for Costa OS version 1.0. For the latest information, check the [GitHub repository](https://github.com/superninjv/costa-os).*
