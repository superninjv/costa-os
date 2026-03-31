#!/usr/bin/env python3
"""Costa AST Daemon — System-wide tree-sitter AST service.

Provides structural code understanding to all Costa OS consumers via D-Bus:
  - AI router (query classification, context injection)
  - MCP server (ast_symbols, ast_scope, ast_complexity tools)
  - AGS shell widgets (Git widget enrichment, code intelligence)
  - Claude Code plugins (efficient delegation decisions)

Architecture:
  - D-Bus session bus: org.costa.AST
  - File watching via GLib.FileMonitor (inotify on Linux)
  - Incremental tree-sitter parsing (~1ms per file, sub-ms updates)
  - LRU cache for parsed ASTs (2000 files max)

Launch: /usr/bin/python3 ast_daemon.py
Kill:   busctl --user call org.costa.AST /org/costa/AST org.costa.AST Shutdown
"""

import json
import os
import signal
import sys
import threading
from pathlib import Path

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib, Gio

# Ensure our directory is in path for ast_parser import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ast_parser

BUS_NAME = "org.costa.AST"
OBJECT_PATH = "/org/costa/AST"
IFACE_NAME = "org.costa.AST"

# Directories to ignore when watching
IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".tox", ".venv", "venv", ".eggs", "dist", "build", ".next", ".nuxt",
    "target", "out", ".cache", ".parcel-cache", ".turbo",
}

# File size limit for parsing (2MB)
MAX_FILE_SIZE = 2 * 1024 * 1024


class ASTService(dbus.service.Object):
    """D-Bus service exposing tree-sitter AST operations."""

    def __init__(self, bus_name):
        super().__init__(bus_name, OBJECT_PATH)
        self._monitors: dict[str, list[Gio.FileMonitor]] = {}  # dir → [monitors]
        self._watched_dirs: set[str] = set()
        self._lock = threading.Lock()
        print(f"costa-ast: service registered on {BUS_NAME}", flush=True)

    # ── Properties ──────────────────────────────────────────────

    @dbus.service.method(dbus.PROPERTIES_IFACE,
                         in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if interface != IFACE_NAME:
            raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")
        if prop == "WatchedDirs":
            return dbus.Array(sorted(self._watched_dirs), signature="s")
        elif prop == "ParsedFiles":
            return dbus.UInt32(ast_parser.get_cache_stats()["cached_files"])
        elif prop == "SupportedLanguages":
            return dbus.Array(ast_parser.get_supported_languages(), signature="s")
        raise dbus.exceptions.DBusException(f"Unknown property: {prop}")

    @dbus.service.method(dbus.PROPERTIES_IFACE,
                         in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != IFACE_NAME:
            return {}
        return {
            "WatchedDirs": dbus.Array(sorted(self._watched_dirs), signature="s"),
            "ParsedFiles": dbus.UInt32(ast_parser.get_cache_stats()["cached_files"]),
            "SupportedLanguages": dbus.Array(
                ast_parser.get_supported_languages(), signature="s"
            ),
        }

    # ── Signals ─────────────────────────────────────────────────

    @dbus.service.signal(IFACE_NAME, signature="ss")
    def FileChanged(self, path, change_type):
        pass

    @dbus.service.signal(IFACE_NAME, signature="s")
    def SymbolsUpdated(self, path):
        pass

    @dbus.service.signal(dbus.PROPERTIES_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    # ── Core Methods ────────────────────────────────────────────

    @dbus.service.method(IFACE_NAME, in_signature="s", out_signature="s")
    def ParseFile(self, path):
        """Parse a file and return its symbol summary as JSON."""
        path = os.path.realpath(str(path))
        result = ast_parser.get_file_summary(path)
        return json.dumps(result)

    @dbus.service.method(IFACE_NAME, in_signature="s", out_signature="s")
    def GetSymbols(self, path):
        """Get all symbols (functions, classes, etc.) from a file."""
        path = os.path.realpath(str(path))
        symbols = ast_parser.get_symbols(path)
        return json.dumps(symbols)

    @dbus.service.method(IFACE_NAME, in_signature="suu", out_signature="s")
    def GetScope(self, path, line, col):
        """Get the scope chain at a position (1-indexed line, 0-indexed col)."""
        path = os.path.realpath(str(path))
        scope = ast_parser.get_scope(path, int(line), int(col))
        return json.dumps(scope)

    @dbus.service.method(IFACE_NAME, in_signature="ssas", out_signature="s")
    def GetDependents(self, path, symbol_name, search_dirs):
        """Find files referencing a symbol. search_dirs limits scope."""
        path = os.path.realpath(str(path))
        dirs = [str(d) for d in search_dirs] if search_dirs else None
        deps = ast_parser.get_dependents(path, str(symbol_name), dirs)
        return json.dumps(deps)

    @dbus.service.method(IFACE_NAME, in_signature="s", out_signature="s")
    def GetComplexity(self, path):
        """Get cyclomatic complexity for each function in a file."""
        path = os.path.realpath(str(path))
        result = ast_parser.get_complexity(path)
        return json.dumps(result)

    @dbus.service.method(IFACE_NAME, in_signature="ss", out_signature="s")
    def IsAdditiveChange(self, diff_text, path):
        """Analyze a diff to determine if changes are purely additive."""
        path = os.path.realpath(str(path))
        result = ast_parser.is_additive_change(str(diff_text), path)
        return json.dumps(result)

    @dbus.service.method(IFACE_NAME, in_signature="s", out_signature="s")
    def GetFileSummary(self, path):
        """Get a structural summary suitable for AI context injection."""
        path = os.path.realpath(str(path))
        result = ast_parser.get_file_summary(path)
        return json.dumps(result)

    @dbus.service.method(IFACE_NAME, in_signature="", out_signature="s")
    def GetStatus(self):
        """Get daemon status and cache statistics."""
        stats = ast_parser.get_cache_stats()
        stats["watched_dirs"] = sorted(self._watched_dirs)
        stats["monitor_count"] = sum(
            len(mons) for mons in self._monitors.values()
        )
        return json.dumps(stats)

    # ── Directory Watching ──────────────────────────────────────

    @dbus.service.method(IFACE_NAME, in_signature="sb", out_signature="b")
    def WatchDirectory(self, path, recursive):
        """Start watching a directory for file changes.

        When files change, they are re-parsed and SymbolsUpdated is emitted.
        """
        path = os.path.realpath(str(path))
        if not os.path.isdir(path):
            return False

        if path in self._watched_dirs:
            return True  # already watching

        with self._lock:
            monitors = []
            self._setup_monitors(path, bool(recursive), monitors)
            self._monitors[path] = monitors
            self._watched_dirs.add(path)

        # Initial parse of existing files
        self._initial_parse(path, bool(recursive))

        self.PropertiesChanged(
            IFACE_NAME,
            {"WatchedDirs": dbus.Array(sorted(self._watched_dirs), signature="s")},
            [],
        )
        print(f"costa-ast: watching {path} (recursive={recursive})", flush=True)
        return True

    @dbus.service.method(IFACE_NAME, in_signature="s", out_signature="b")
    def UnwatchDirectory(self, path):
        """Stop watching a directory."""
        path = os.path.realpath(str(path))
        if path not in self._watched_dirs:
            return False

        with self._lock:
            monitors = self._monitors.pop(path, [])
            for mon in monitors:
                mon.cancel()
            self._watched_dirs.discard(path)

        self.PropertiesChanged(
            IFACE_NAME,
            {"WatchedDirs": dbus.Array(sorted(self._watched_dirs), signature="s")},
            [],
        )
        print(f"costa-ast: unwatched {path}", flush=True)
        return True

    @dbus.service.method(IFACE_NAME, in_signature="", out_signature="")
    def Shutdown(self):
        """Gracefully stop the daemon."""
        print("costa-ast: shutdown requested via D-Bus", flush=True)
        GLib.idle_add(self._quit)

    def _quit(self):
        loop.quit()
        return False

    # ── File Monitoring Internals ───────────────────────────────

    def _setup_monitors(self, dirpath: str, recursive: bool,
                        monitors: list):
        """Set up GLib file monitors for a directory."""
        try:
            gfile = Gio.File.new_for_path(dirpath)
            monitor = gfile.monitor_directory(
                Gio.FileMonitorFlags.NONE, None
            )
            monitor.connect("changed", self._on_file_changed)
            monitors.append(monitor)
        except Exception as e:
            print(f"costa-ast: monitor error for {dirpath}: {e}", flush=True)
            return

        if not recursive:
            return

        try:
            for entry in os.scandir(dirpath):
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in IGNORE_DIRS or entry.name.startswith("."):
                        continue
                    self._setup_monitors(entry.path, True, monitors)
        except PermissionError:
            pass

    def _on_file_changed(self, monitor, gfile, other_file, event_type):
        """Handle file change events from GLib.FileMonitor."""
        if event_type not in (
            Gio.FileMonitorEvent.CHANGED,
            Gio.FileMonitorEvent.CREATED,
            Gio.FileMonitorEvent.DELETED,
        ):
            return

        filepath = gfile.get_path()
        if not filepath:
            return

        # Skip non-parseable files early
        if not ast_parser.detect_language(filepath):
            return

        # Skip large files
        try:
            if event_type != Gio.FileMonitorEvent.DELETED:
                if os.path.getsize(filepath) > MAX_FILE_SIZE:
                    return
        except OSError:
            pass

        if event_type == Gio.FileMonitorEvent.DELETED:
            ast_parser.invalidate_file(filepath)
            change_type = "deleted"
        elif event_type == Gio.FileMonitorEvent.CREATED:
            ast_parser.parse_file(filepath)
            change_type = "created"
        else:
            # Re-parse on change
            old_pf = ast_parser._file_cache.get(os.path.realpath(filepath))
            old_symbols = old_pf.symbols if old_pf else None
            pf = ast_parser.parse_file(filepath, force=True)
            change_type = "modified"

            # Emit SymbolsUpdated if symbols actually changed
            if pf:
                new_symbols = ast_parser.get_symbols(filepath)
                if new_symbols != old_symbols:
                    self.SymbolsUpdated(filepath)

        self.FileChanged(filepath, change_type)

        # Update ParsedFiles property
        self.PropertiesChanged(
            IFACE_NAME,
            {"ParsedFiles": dbus.UInt32(
                ast_parser.get_cache_stats()["cached_files"]
            )},
            [],
        )

    def _initial_parse(self, dirpath: str, recursive: bool):
        """Parse all existing files in a directory (background thread)."""
        def _do_parse():
            count = 0
            for root, dirs, files in os.walk(dirpath):
                # Filter ignored dirs
                dirs[:] = [
                    d for d in dirs
                    if d not in IGNORE_DIRS and not d.startswith(".")
                ]
                if not recursive:
                    dirs.clear()

                for fname in files:
                    fp = os.path.join(root, fname)
                    if ast_parser.detect_language(fp):
                        try:
                            if os.path.getsize(fp) <= MAX_FILE_SIZE:
                                ast_parser.parse_file(fp)
                                count += 1
                        except OSError:
                            pass

            print(f"costa-ast: initial parse of {dirpath}: {count} files", flush=True)

            # Update property on main thread
            GLib.idle_add(
                lambda: self.PropertiesChanged(
                    IFACE_NAME,
                    {"ParsedFiles": dbus.UInt32(
                        ast_parser.get_cache_stats()["cached_files"]
                    )},
                    [],
                ) or False
            )

        thread = threading.Thread(target=_do_parse, daemon=True)
        thread.start()


# ── Auto-watch common project directories ───────────────────────

def auto_watch(service: ASTService):
    """Watch ~/projects/ subdirectories automatically."""
    projects_dir = os.path.expanduser("~/projects")
    if not os.path.isdir(projects_dir):
        return

    try:
        for entry in os.scandir(projects_dir):
            if entry.is_dir(follow_symlinks=False) and not entry.name.startswith("."):
                service.WatchDirectory(entry.path, True)
    except OSError:
        pass


# ── Main ────────────────────────────────────────────────────────

loop = None


def main():
    global loop

    # Set up GLib main loop for D-Bus
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    # Acquire the bus name
    try:
        bus = dbus.SessionBus()
        bus_name = dbus.service.BusName(
            BUS_NAME, bus,
            do_not_queue=True,
            replace_existing=False,
        )
    except dbus.exceptions.NameExistsException:
        print("costa-ast: another instance is already running", file=sys.stderr)
        sys.exit(1)

    service = ASTService(bus_name)

    # Handle signals
    def _shutdown(*_):
        print("costa-ast: signal received, shutting down", flush=True)
        loop.quit()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Auto-watch project directories
    GLib.idle_add(lambda: auto_watch(service) or False)

    # Run
    loop = GLib.MainLoop()
    print("costa-ast: daemon running", flush=True)

    try:
        loop.run()
    except KeyboardInterrupt:
        pass

    # Cleanup monitors
    for monitors in service._monitors.values():
        for mon in monitors:
            mon.cancel()

    print("costa-ast: stopped", flush=True)


if __name__ == "__main__":
    main()
