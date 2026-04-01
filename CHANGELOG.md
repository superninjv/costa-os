# Costa OS Changelog

## 1.3.2 — 2026-04-01

### Security
- Sanitized 17,000+ personal path references from ML training data
- Added sensitive-path denylist and secret redaction to context gatherer (prevents config file contents from reaching cloud APIs)
- Hardened MCP server command deny list (added `node -e`, `ruby -e`, `lua -e`, `php -r`, backtick and `$()` substitution)
- Switched router command execution from `shell=True` to `shlex.split` (argv list)
- Moved AI queue socket, VAD daemon, and PTT files from `/tmp/` to `$XDG_RUNTIME_DIR` with 0600 permissions
- Firecrawl docker-compose: replaced hardcoded weak passwords with required environment variables

### Fixed
- Hardcoded `/home/jack` paths in benchmark scripts, AirPods widget, navigator agent, and test scripts
- Example API key patterns in docs replaced with generic placeholders
- Demo scripts no longer reference personal project names or use `--dangerously-skip-permissions`

### Changed
- Demo scripts parameterized: monitor name, project directories, and expected monitor count are now configurable via environment variables

## 1.3.1 — 2026-03-31

### Changed
- Benchmark runner default: num_predict 512→2048, num_ctx 4096→8192
- Router updated for 2048-token benchmarks, both ML stages retrained
- LLM judge switched from Claude Haiku to free-tier models (Gemini Flash Lite / Mistral Devstral)
- VRAM manager: qwen2.5 → qwen3.5/qwen3, default tier full→medium, thresholds updated

## 1.0.9 — 2026-03-20

### Added
- Version numbering system (VERSION file, git tags, ISO filename stamping)
- `costa-update` command — AI-assisted system updates with Claude/local model fallback
- Settings Hub: version display and update button in System section
- `bump-version.sh` developer tool for release management
- `upload-iso.sh` developer tool for DO Spaces deployment

### Changed
- Build script now stamps version into ISO filename
- Settings Hub "System Update" replaced with versioned Costa OS update flow
- Removed Obsidian MCP server (redundant — native file tools access vault directly)
- Claude Code child sessions now get nav-first tool priority via wrapper

### Fixed
- Hyprland "started without start-hyprland" warning (greetd config updated)
- claude-code-enhanced child sessions missing `claude` binary in PATH
