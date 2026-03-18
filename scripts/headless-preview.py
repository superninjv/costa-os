#!/usr/bin/env python3
"""Costa OS — Headless Monitor Preview

Floating window showing a live-updating scaled screenshot of Claude's
headless virtual monitor. Toggle from waybar or CLI.

Single-instance: re-running closes the existing window.
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
import subprocess
import os
import sys
import signal

PID_FILE = "/tmp/costa-headless-preview.pid"
SCREENSHOT_PATH = "/tmp/costa-headless-preview.png"
PREVIEW_WIDTH = 480
REFRESH_MS = 2000
COSTA_DIR = os.path.expanduser("~/.config/costa")

CSS = """
window {
    background-color: #161821;
    border: 2px solid #5b94a8;
    border-radius: 12px;
}

.preview-header {
    background-color: #1b1d2b;
    padding: 6px 12px;
    border-radius: 10px 10px 0 0;
}

.preview-title {
    color: #5b94a8;
    font-family: "JetBrains Mono Nerd Font", monospace;
    font-size: 12px;
    font-weight: bold;
}

.preview-status {
    color: #9a9eb5;
    font-family: "JetBrains Mono Nerd Font", monospace;
    font-size: 11px;
}

.preview-image {
    margin: 4px;
    border-radius: 0 0 10px 10px;
}

.preview-empty {
    color: #545870;
    font-size: 14px;
    padding: 40px;
}
"""


def get_headless_monitor():
    """Find the headless monitor name."""
    # Try config file first
    nav_conf = os.path.join(COSTA_DIR, "nav.conf")
    if os.path.exists(nav_conf):
        for line in open(nav_conf):
            if line.startswith("COSTA_NAV_MONITOR="):
                name = line.split("=", 1)[1].strip()
                if name:
                    return name

    # Try environment
    env_mon = os.environ.get("COSTA_NAV_MONITOR")
    if env_mon:
        return env_mon

    # Auto-detect from hyprctl
    try:
        out = subprocess.check_output(
            ["hyprctl", "monitors", "-j"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode()
        import json
        for m in json.loads(out):
            if m["name"].startswith("HEADLESS"):
                return m["name"]
    except Exception:
        pass

    return None


def capture_headless(monitor_name):
    """Capture screenshot of the headless monitor. Returns True on success."""
    try:
        subprocess.run(
            ["grim", "-o", monitor_name, SCREENSHOT_PATH],
            capture_output=True, timeout=5,
        )
        return os.path.exists(SCREENSHOT_PATH)
    except Exception:
        return False


def get_headless_info(monitor_name):
    """Get info about what's on the headless monitor."""
    try:
        import json

        # Get monitor ID
        mon_out = subprocess.check_output(
            ["hyprctl", "monitors", "-j"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode()
        mon_id = None
        for m in json.loads(mon_out):
            if m["name"] == monitor_name:
                mon_id = m["id"]
                break
        if mon_id is None:
            return "Monitor not found"

        # Get windows on that monitor
        out = subprocess.check_output(
            ["hyprctl", "clients", "-j"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode()
        windows = []
        for c in json.loads(out):
            if c.get("monitor") == mon_id:
                title = c.get("title", "")
                cls = c.get("class", "")
                label = title[:40] if title else cls
                if label:
                    windows.append(label)

        if windows:
            return f"{len(windows)} window{'s' if len(windows) != 1 else ''}: {windows[0]}"
        return "Empty"
    except Exception:
        return ""


class HeadlessPreview(Gtk.Window):
    def __init__(self):
        super().__init__(title="headless-preview")
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_resizable(False)

        # Load CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self.monitor_name = get_headless_monitor()
        self.preview_height = 270  # Will be recalculated from aspect ratio

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(main_box)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.get_style_context().add_class("preview-header")

        icon = Gtk.Label(label="󰍹")
        icon.get_style_context().add_class("preview-title")
        header.pack_start(icon, False, False, 0)

        title = Gtk.Label(label="Claude's Screen")
        title.get_style_context().add_class("preview-title")
        header.pack_start(title, False, False, 0)

        self.status_label = Gtk.Label(label="")
        self.status_label.get_style_context().add_class("preview-status")
        self.status_label.set_xalign(1.0)
        header.pack_end(self.status_label, True, True, 0)

        close_btn = Gtk.Button(label="󰅖")
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.get_style_context().add_class("preview-title")
        close_btn.connect("clicked", lambda _: Gtk.main_quit())
        header.pack_end(close_btn, False, False, 0)

        main_box.pack_start(header, False, False, 0)

        # Image area
        self.image = Gtk.Image()
        self.image.get_style_context().add_class("preview-image")

        self.empty_label = Gtk.Label(label="No headless monitor detected")
        self.empty_label.get_style_context().add_class("preview-empty")

        self.stack = Gtk.Stack()
        self.stack.add_named(self.image, "preview")
        self.stack.add_named(self.empty_label, "empty")
        main_box.pack_start(self.stack, True, True, 0)

        if self.monitor_name:
            self.status_label.set_text(self.monitor_name)
            self._refresh()
            GLib.timeout_add(REFRESH_MS, self._refresh)
        else:
            self.stack.set_visible_child_name("empty")
            self.set_size_request(PREVIEW_WIDTH, 120)

        self.connect("key-press-event", self._on_key)
        self.show_all()

    def _refresh(self):
        if not self.monitor_name:
            return False

        if capture_headless(self.monitor_name):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(SCREENSHOT_PATH)
                orig_w = pixbuf.get_width()
                orig_h = pixbuf.get_height()

                scale = PREVIEW_WIDTH / orig_w
                scaled_h = int(orig_h * scale)
                self.preview_height = scaled_h

                scaled = pixbuf.scale_simple(
                    PREVIEW_WIDTH, scaled_h,
                    GdkPixbuf.InterpType.BILINEAR,
                )
                self.image.set_from_pixbuf(scaled)
                self.stack.set_visible_child_name("preview")
                self.set_size_request(PREVIEW_WIDTH, scaled_h + 32)
            except Exception:
                self.stack.set_visible_child_name("empty")
                self.empty_label.set_text("Capture failed")
        else:
            self.stack.set_visible_child_name("empty")
            self.empty_label.set_text("Capture failed")

        # Update status with window info
        info = get_headless_info(self.monitor_name)
        self.status_label.set_text(info)

        return True

    def _on_key(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()


def kill_existing():
    """Kill any existing preview instance."""
    if os.path.exists(PID_FILE):
        try:
            pid = int(open(PID_FILE).read().strip())
            os.kill(pid, signal.SIGTERM)
            os.remove(PID_FILE)
            return True
        except (ProcessLookupError, ValueError):
            try:
                os.remove(PID_FILE)
            except OSError:
                pass
    return False


def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def cleanup(*_):
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    try:
        os.remove(SCREENSHOT_PATH)
    except OSError:
        pass
    Gtk.main_quit()


def main():
    # Toggle behavior: if already running, kill it and exit
    if kill_existing():
        sys.exit(0)

    write_pid()
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    win = HeadlessPreview()
    win.connect("destroy", cleanup)

    Gtk.main()


if __name__ == "__main__":
    main()
