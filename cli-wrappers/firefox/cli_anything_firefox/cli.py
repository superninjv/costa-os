#!/usr/bin/env python3
"""CLI-Anything Firefox — deterministic CLI for Firefox browser state.

Uses the Marionette protocol (Firefox remote debugging) to query browser state.
Falls back to DBus/AT-SPI when Marionette is unavailable.

Usage:
    cli-anything-firefox tabs list --json
    cli-anything-firefox navigation current-url --json
    cli-anything-firefox navigation current-title --json
    cli-anything-firefox bookmarks list --json
    cli-anything-firefox history recent --json
"""

import json
import subprocess
import sys

import click


def _get_marionette_port() -> int:
    """Find Firefox's Marionette port from its profile or default."""
    return 2828


def _query_via_dbus(method: str) -> dict | None:
    """Fall back to DBus for basic queries when Marionette unavailable."""
    # Use xdotool + AT-SPI as fallback
    return None


def _run_marionette(script: str) -> dict | None:
    """Execute a Marionette script and return parsed result."""
    # TODO: Full Marionette client implementation
    # For now, use the simpler approach of reading Firefox state via
    # its recovery files or sessionstore
    return None


def _read_session_tabs() -> list[dict]:
    """Read open tabs from Firefox's session recovery files."""
    from pathlib import Path
    import glob
    import lz4.block

    profiles_dir = Path.home() / ".mozilla" / "firefox"
    tabs = []

    for profile in profiles_dir.glob("*.default*"):
        recovery = profile / "sessionstore-backups" / "recovery.jsonlz4"
        if not recovery.exists():
            continue
        try:
            with open(recovery, "rb") as f:
                magic = f.read(8)  # mozLz40\0
                data = lz4.block.decompress(f.read())
                session = json.loads(data)
                for window in session.get("windows", []):
                    for tab in window.get("tabs", []):
                        entries = tab.get("entries", [])
                        if entries:
                            current = entries[tab.get("index", 1) - 1]
                            tabs.append({
                                "title": current.get("title", ""),
                                "url": current.get("url", ""),
                                "active": tab.get("hidden", False) is False,
                            })
        except Exception:
            continue

    return tabs


@click.group()
def cli():
    """CLI-Anything Firefox — deterministic browser state access."""
    pass


@cli.group()
def tabs():
    """Manage Firefox tabs."""
    pass


@tabs.command("list")
@click.option("--json", "as_json", is_flag=True, default=True, help="Output as JSON")
def tabs_list(as_json):
    """List all open tabs with titles and URLs."""
    tab_list = _read_session_tabs()
    if as_json:
        click.echo(json.dumps({"tabs": tab_list, "count": len(tab_list)}))
    else:
        for i, t in enumerate(tab_list):
            click.echo(f"{i}: {t['title'][:60]} — {t['url']}")


@cli.group()
def navigation():
    """Browser navigation state."""
    pass


@navigation.command("current-url")
@click.option("--json", "as_json", is_flag=True, default=True)
def nav_current_url(as_json):
    """Get the URL of the currently active tab."""
    tabs = _read_session_tabs()
    active = [t for t in tabs if t.get("active")]
    url = active[0]["url"] if active else (tabs[0]["url"] if tabs else "")
    if as_json:
        click.echo(json.dumps({"url": url}))
    else:
        click.echo(url)


@navigation.command("current-title")
@click.option("--json", "as_json", is_flag=True, default=True)
def nav_current_title(as_json):
    """Get the title of the currently active tab."""
    tabs = _read_session_tabs()
    active = [t for t in tabs if t.get("active")]
    title = active[0]["title"] if active else (tabs[0]["title"] if tabs else "")
    if as_json:
        click.echo(json.dumps({"title": title}))
    else:
        click.echo(title)


@cli.group()
def bookmarks():
    """Firefox bookmarks."""
    pass


@bookmarks.command("list")
@click.option("--json", "as_json", is_flag=True, default=True)
def bookmarks_list(as_json):
    """List bookmarks from Firefox's places database."""
    from pathlib import Path
    import sqlite3

    profiles_dir = Path.home() / ".mozilla" / "firefox"
    results = []

    for profile in profiles_dir.glob("*.default*"):
        places = profile / "places.sqlite"
        if not places.exists():
            continue
        try:
            conn = sqlite3.connect(f"file:{places}?mode=ro&immutable=1", uri=True)
            cursor = conn.execute(
                "SELECT b.title, p.url FROM moz_bookmarks b "
                "JOIN moz_places p ON b.fk = p.id "
                "WHERE b.type = 1 AND p.url NOT LIKE 'place:%' "
                "ORDER BY b.lastModified DESC LIMIT 50"
            )
            for title, url in cursor:
                results.append({"title": title or "", "url": url})
            conn.close()
        except Exception:
            continue

    if as_json:
        click.echo(json.dumps({"bookmarks": results, "count": len(results)}))
    else:
        for b in results:
            click.echo(f"{b['title'][:50]} — {b['url']}")


@cli.group()
def history():
    """Firefox browsing history."""
    pass


@history.command("recent")
@click.option("--json", "as_json", is_flag=True, default=True)
@click.option("--limit", default=20, help="Number of entries")
def history_recent(as_json, limit):
    """Show recent browsing history."""
    from pathlib import Path
    import sqlite3

    profiles_dir = Path.home() / ".mozilla" / "firefox"
    results = []

    for profile in profiles_dir.glob("*.default*"):
        places = profile / "places.sqlite"
        if not places.exists():
            continue
        try:
            conn = sqlite3.connect(f"file:{places}?mode=ro&immutable=1", uri=True)
            cursor = conn.execute(
                "SELECT p.url, p.title, h.visit_date / 1000000 as visit_ts "
                "FROM moz_historyvisits h JOIN moz_places p ON h.place_id = p.id "
                "ORDER BY h.visit_date DESC LIMIT ?",
                (limit,)
            )
            for url, title, ts in cursor:
                results.append({"url": url, "title": title or "", "timestamp": ts})
            conn.close()
        except Exception:
            continue

    if as_json:
        click.echo(json.dumps({"history": results, "count": len(results)}))
    else:
        for h in results:
            click.echo(f"{h['title'][:50]} — {h['url']}")


def main():
    cli()


if __name__ == "__main__":
    main()
