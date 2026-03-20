# Costa OS Changelog

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
