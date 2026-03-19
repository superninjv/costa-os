"""CLI-Anything wrapper for Strawberry Music Player — deterministic CLI access to playback and library state.

Uses playerctl (MPRIS2/DBus) for playback control and SQLite for library queries
against Strawberry's collection.db.

Capabilities: playback status, now-playing, queue, library search, library stats
"""

__version__ = "0.1.0"
