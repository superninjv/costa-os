#!/usr/bin/env python3
"""CLI-Anything Strawberry — deterministic CLI for Strawberry Music Player state.

Uses playerctl (MPRIS2) for playback state and SQLite for library queries against
Strawberry's collection.db (~/.local/share/strawberry/strawberry/collection.db).

Usage:
    cli-anything-strawberry playback status --json
    cli-anything-strawberry playback now-playing --json
    cli-anything-strawberry queue list --json
    cli-anything-strawberry library search --json --query "bohemian"
    cli-anything-strawberry library stats --json
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import click

PLAYER = "strawberry"
COLLECTION_DB = Path.home() / ".local" / "share" / "strawberry" / "strawberry" / "collection.db"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _playerctl(*args: str) -> str | None:
    """Run a playerctl command targeting Strawberry. Returns stdout or None on failure."""
    cmd = ["playerctl", "-p", PLAYER, *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return None


def _is_running() -> bool:
    """Check if Strawberry is reachable via playerctl."""
    status = _playerctl("status")
    return status is not None


def _get_metadata(key: str) -> str:
    """Get a single MPRIS metadata value."""
    val = _playerctl("metadata", key)
    return val if val else ""


def _get_all_metadata() -> dict:
    """Get all MPRIS metadata as a dict."""
    raw = _playerctl("metadata", "--format",
                     '{{artist}}\t{{title}}\t{{album}}\t{{mpris:length}}\t{{mpris:artUrl}}')
    if not raw:
        return {}
    parts = raw.split("\t")
    if len(parts) < 5:
        parts.extend([""] * (5 - len(parts)))
    return {
        "artist": parts[0],
        "title": parts[1],
        "album": parts[2],
        "length_us": parts[3],
        "art_url": parts[4],
    }


def _get_position_us() -> int | None:
    """Get current playback position in microseconds."""
    raw = _playerctl("position")
    if raw is None:
        return None
    try:
        return int(float(raw) * 1_000_000)
    except (ValueError, TypeError):
        return None


def _format_time(us: int | None) -> str:
    """Format microseconds as mm:ss."""
    if us is None or us <= 0:
        return "0:00"
    total_sec = us // 1_000_000
    minutes = total_sec // 60
    seconds = total_sec % 60
    return f"{minutes}:{seconds:02d}"


def _open_collection_db() -> sqlite3.Connection | None:
    """Open Strawberry's collection database read-only."""
    if not COLLECTION_DB.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{COLLECTION_DB}?mode=ro&immutable=1", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def _error_response(message: str) -> dict:
    return {"error": message}


def _output(data: dict, as_json: bool = True):
    """Print output in JSON or plain text."""
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        for k, v in data.items():
            click.echo(f"{k}: {v}")


# ---------------------------------------------------------------------------
# CLI structure
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """CLI-Anything Strawberry — deterministic music player state access."""
    pass


# -- Playback ---------------------------------------------------------------

@cli.group()
def playback():
    """Playback state and controls."""
    pass


@playback.command("status")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def playback_status(as_json):
    """Full playback status: track, artist, album, position, duration, state."""
    if not _is_running():
        _output(_error_response("Strawberry is not running or not reachable via MPRIS"), as_json)
        return

    status = _playerctl("status") or "Unknown"
    meta = _get_all_metadata()
    position_us = _get_position_us()

    try:
        length_us = int(meta.get("length_us", 0))
    except (ValueError, TypeError):
        length_us = 0

    data = {
        "state": status.lower(),
        "artist": meta.get("artist", ""),
        "title": meta.get("title", ""),
        "album": meta.get("album", ""),
        "position": _format_time(position_us),
        "position_us": position_us,
        "duration": _format_time(length_us),
        "duration_us": length_us,
        "art_url": meta.get("art_url", ""),
    }
    _output(data, as_json)


@playback.command("now-playing")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def playback_now_playing(as_json):
    """Simple now-playing: artist, title, album."""
    if not _is_running():
        _output(_error_response("Strawberry is not running or not reachable via MPRIS"), as_json)
        return

    meta = _get_all_metadata()
    data = {
        "artist": meta.get("artist", ""),
        "title": meta.get("title", ""),
        "album": meta.get("album", ""),
    }
    _output(data, as_json)


# -- Queue -------------------------------------------------------------------

@cli.group()
def queue():
    """Current playlist / queue."""
    pass


@queue.command("list")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--limit", default=50, help="Max tracks to return")
def queue_list(as_json, limit):
    """List tracks in the current playlist/queue.

    Attempts to read from Strawberry's playlist tables in collection.db.
    Falls back to showing just the current track if DB access fails.
    """
    # Try reading from Strawberry's DB — it stores playlists in the DB
    conn = _open_collection_db()
    tracks = []

    if conn:
        try:
            # Strawberry stores playlist tracks in playlist_items or similar tables
            # The main playlist table varies by version; try common schemas
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%playlist%'"
            )
            playlist_tables = [row[0] for row in cursor]

            if "playlist_items" in playlist_tables:
                cursor = conn.execute(
                    "SELECT title, artist, album, length "
                    "FROM playlist_items ORDER BY rowid LIMIT ?",
                    (limit,)
                )
                for row in cursor:
                    tracks.append({
                        "title": row["title"] or "",
                        "artist": row["artist"] or "",
                        "album": row["album"] or "",
                        "duration": _format_time((row["length"] or 0) * 1_000_000)
                        if row["length"] else "",
                    })
            conn.close()
        except sqlite3.Error:
            if conn:
                conn.close()

    # If no playlist data from DB, show current track as fallback
    if not tracks:
        if _is_running():
            meta = _get_all_metadata()
            if meta.get("title"):
                tracks.append({
                    "title": meta.get("title", ""),
                    "artist": meta.get("artist", ""),
                    "album": meta.get("album", ""),
                    "duration": "",
                    "note": "Queue data unavailable; showing current track only",
                })

    data = {"tracks": tracks, "count": len(tracks)}
    _output(data, as_json)


# -- Library -----------------------------------------------------------------

@cli.group()
def library():
    """Music library queries (via collection.db)."""
    pass


@library.command("search")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
@click.option("--query", "-q", required=True, help="Search text (matches title, artist, album)")
@click.option("--limit", default=25, help="Max results")
def library_search(as_json, query, limit):
    """Search the music library by title, artist, or album name."""
    conn = _open_collection_db()
    if not conn:
        _output(_error_response(
            f"Collection database not found at {COLLECTION_DB}. "
            "Is Strawberry installed and has it scanned your library?"
        ), as_json)
        return

    try:
        like = f"%{query}%"
        cursor = conn.execute(
            "SELECT title, artist, album, albumartist, track, year, length, "
            "filename, filetype, samplerate, bitrate "
            "FROM songs "
            "WHERE title LIKE ? OR artist LIKE ? OR album LIKE ? OR albumartist LIKE ? "
            "ORDER BY artist, album, track "
            "LIMIT ?",
            (like, like, like, like, limit)
        )
        results = []
        for row in cursor:
            results.append({
                "title": row["title"] or "",
                "artist": row["artist"] or "",
                "album": row["album"] or "",
                "album_artist": row["albumartist"] or "",
                "track": row["track"] or 0,
                "year": row["year"] or 0,
                "duration": _format_time((row["length"] or 0) * 1_000),
                "duration_ms": row["length"] or 0,
                "filename": row["filename"] or "",
                "filetype": row["filetype"] or "",
                "sample_rate": row["samplerate"] or 0,
                "bitrate": row["bitrate"] or 0,
            })
        conn.close()
        _output({"results": results, "count": len(results), "query": query}, as_json)
    except sqlite3.Error as e:
        conn.close()
        _output(_error_response(f"Database query failed: {e}"), as_json)


@library.command("stats")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def library_stats(as_json):
    """Library statistics: total tracks, albums, artists."""
    conn = _open_collection_db()
    if not conn:
        _output(_error_response(
            f"Collection database not found at {COLLECTION_DB}. "
            "Is Strawberry installed and has it scanned your library?"
        ), as_json)
        return

    try:
        total_tracks = conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
        total_albums = conn.execute("SELECT COUNT(DISTINCT album) FROM songs WHERE album != ''").fetchone()[0]
        total_artists = conn.execute("SELECT COUNT(DISTINCT artist) FROM songs WHERE artist != ''").fetchone()[0]
        total_album_artists = conn.execute(
            "SELECT COUNT(DISTINCT albumartist) FROM songs WHERE albumartist != ''"
        ).fetchone()[0]

        # Total duration
        total_length = conn.execute("SELECT SUM(length) FROM songs").fetchone()[0] or 0
        total_hours = total_length / 1_000 / 3600  # length is in ms

        # File type breakdown
        cursor = conn.execute(
            "SELECT filetype, COUNT(*) as cnt FROM songs GROUP BY filetype ORDER BY cnt DESC"
        )
        filetypes = {row["filetype"]: row["cnt"] for row in cursor}

        conn.close()
        _output({
            "total_tracks": total_tracks,
            "total_albums": total_albums,
            "total_artists": total_artists,
            "total_album_artists": total_album_artists,
            "total_duration_hours": round(total_hours, 1),
            "filetypes": filetypes,
        }, as_json)
    except sqlite3.Error as e:
        conn.close()
        _output(_error_response(f"Database query failed: {e}"), as_json)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    cli()


if __name__ == "__main__":
    main()
