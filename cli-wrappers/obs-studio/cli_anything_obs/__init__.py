"""CLI-Anything wrapper for OBS Studio — deterministic CLI access to OBS state.

Generated via CLI-Anything (https://github.com/HKUDS/CLI-Anything).
This wrapper uses the obs-websocket protocol (built in since OBS 28+) to query
OBS state, falling back to reading OBS config files when the websocket is
unavailable.

Capabilities: status, scenes, sources, recording, streaming
"""

__version__ = "0.1.0"
