"""CLI-Anything wrapper for MPV media player — deterministic CLI access to playback state.

Uses MPV's IPC socket (JSON protocol) as primary interface, with playerctl (MPRIS2)
as fallback when the socket is unavailable.

Capabilities: playback status, now-playing, playlist, arbitrary property queries
"""

__version__ = "0.1.0"
