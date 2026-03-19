"""CLI-Anything wrapper for Steam — deterministic CLI access to Steam library state.

Parses VDF/ACF config files from ~/.local/share/Steam/ to expose game library,
download status, and running state without depending on Steam's own CLI.

Capabilities: library, game info, running status, downloads
"""

__version__ = "0.1.0"
