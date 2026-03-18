---
l0: "Clipboard intelligence: auto-classifies clipboard content and offers contextual actions like debug errors, open URLs, run commands"
l1_sections: ["What Is Clipboard Intelligence", "Content Types Detected", "How It Works", "Actions by Content Type", "Clipboard History", "Service Management", "Configuration"]
tags: [clipboard, intelligence, classify, error, url, json, code, command, debug, ai, notification, cliphist, wl-copy, wl-paste]
---

# Clipboard Intelligence

## What Is Clipboard Intelligence
Clipboard Intelligence is a background daemon that watches your clipboard, classifies what you copied, and shows a notification with smart actions. Copy an error message and it offers to ask AI to debug it. Copy a URL and it offers to open it. Copy a shell command and it offers to run it.

## Content Types Detected
The classifier recognizes these content types:
- **Error messages** — stack traces, tracebacks, compiler errors, log errors
- **URLs** — http/https links, localhost URLs, IP addresses
- **JSON** — valid JSON objects or arrays
- **File paths** — absolute or relative paths to files/directories
- **Shell commands** — lines starting with common commands (sudo, git, docker, npm, etc.)
- **Code snippets** — detected by language (Python, JavaScript, Rust, Java, Bash, etc.)
- **Plain text** — anything that doesn't match the above

## How It Works
1. Background daemon (`costa-clipboard-daemon`) monitors clipboard via `wl-paste --watch`
2. Each new clipboard entry is classified using pattern matching + the local AI model
3. A dunst notification appears with the detected type and available actions
4. Click the notification action button to execute
5. All clipboard entries are stored in cliphist for history

The daemon runs as a systemd user service and starts automatically on login.

## Actions by Content Type

### How do I debug an error I copied?
Copy any error message (stack trace, compiler error, etc.) and a notification appears:
- **"Ask AI to Debug"** — sends the error to costa-ai with context about your current project
- **"Search Web"** — opens a browser search for the error text
- **"Copy Clean"** — strips ANSI codes and line numbers, re-copies clean text

### How do I open a URL I copied?
Copy a URL and the notification offers:
- **"Open in Browser"** — opens in your default browser
- **"Open in Background"** — opens without switching focus
- **"Preview"** — fetches the page title and shows it in the notification

### How do I run a command I copied?
Copy a shell command and the notification offers:
- **"Run"** — executes the command in a new terminal window
- **"Run Silent"** — executes and only notifies on error
- **"Edit First"** — opens the command in a terminal for editing before execution
- Commands with `sudo`, `rm`, or destructive flags always prompt for confirmation

### How do I work with copied JSON?
Copy JSON and the notification offers:
- **"Pretty Print"** — formats with jq and re-copies
- **"Validate"** — checks for syntax errors
- **"Extract Keys"** — copies just the top-level keys

### How do I work with copied code?
Copy a code snippet and the notification shows the detected language:
- **"Explain"** — sends to AI for explanation
- **"Save to File"** — saves to /tmp/ with correct file extension
- **"Format"** — runs through the appropriate formatter (black, prettier, rustfmt)

### How do I work with copied file paths?
Copy a file path and the notification offers:
- **"Open File"** — opens in your default editor
- **"Open Directory"** — opens the parent directory in file manager
- **"Copy Contents"** — reads the file and puts contents in clipboard

## Clipboard History

### How do I view clipboard history?
```bash
# Open clipboard history picker (rofi)
# Keybind: SUPER+V
cliphist list | rofi -dmenu | cliphist decode | wl-copy
```

### How do I clear clipboard history?
```bash
cliphist wipe
```

### How do I search clipboard history?
SUPER+V opens rofi with clipboard history — just type to filter.

## Service Management

### How do I check if clipboard intelligence is running?
```bash
systemctl --user status costa-clipboard
```

### How do I restart the clipboard daemon?
```bash
systemctl --user restart costa-clipboard
```

### How do I disable clipboard intelligence?
```bash
systemctl --user disable --now costa-clipboard
```
This stops the daemon and prevents it from starting on login. Clipboard still works normally, you just won't get smart notifications.

### How do I re-enable it?
```bash
systemctl --user enable --now costa-clipboard
```

## Configuration
- Config file: `~/.config/costa/clipboard.yaml`
- Options:
  - `enabled: true` — master toggle
  - `classify_with_ai: true` — use local LLM for ambiguous content (slower but smarter)
  - `notification_timeout: 8` — seconds before notification auto-dismisses
  - `dangerous_command_confirm: true` — always confirm before running destructive commands
  - `ignored_apps: []` — list of app classes to ignore clipboard events from (e.g., password managers)
  - `max_history: 1000` — max entries in cliphist
