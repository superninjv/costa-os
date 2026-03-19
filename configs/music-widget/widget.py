#!/usr/bin/env python3
"""Costa Music Widget — MPRIS controller with Strawberry library browsing.

Features:
  - Now playing display with album art, progress, seek
  - Cold start: launches Strawberry and plays if not running
  - Queue view: current playlist tracks, click to jump
  - Search: search Strawberry's SQLite library by title/artist/album
  - Playlist switching via D-Bus
  - Hide/minimize Strawberry button
  - Player switcher for multi-player setups (Firefox, Spotify, etc.)
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango
import subprocess
import sqlite3
import os
import sys
import hashlib
import urllib.request
import signal
import json

WIDGET_WIDTH = 420
WIDGET_HEIGHT = 680
ART_SIZE = 140
CACHE_DIR = os.path.expanduser("~/.cache/costa-music-widget")
PID_FILE = "/tmp/costa-music.pid"
STRAWBERRY_DB = os.path.expanduser(
    "~/.local/share/strawberry/strawberry/strawberry.db")

os.makedirs(CACHE_DIR, exist_ok=True)

PLAYER_ICONS = {
    "spotify": "\uf1bc",
    "firefox": "󰈹",
    "chromium": "",
    "chrome": "",
    "brave": "󰖟",
    "vlc": "󰕼",
    "mpv": "",
    "strawberry": "󰎆",
    "cmus": "󰎆",
    "rhythmbox": "󰎆",
    "audacious": "󰎆",
    "clementine": "󰎆",
    "elisa": "󰎆",
    "celluloid": "",
    "totem": "",
}

CSS = """
@define-color base       #1b1d2b;
@define-color mantle     #161821;
@define-color surface0   #252836;
@define-color surface1   #2f3345;
@define-color surface2   #3a3e52;
@define-color text       #d4cfc4;
@define-color dim        #8b8e9b;
@define-color sea        #5b94a8;
@define-color foam       #7eb5b0;
@define-color terracotta #c27849;
@define-color sand       #c9a96e;
@define-color lavender   #9884b8;

window {
    background-color: @base;
    border: 1px solid @surface2;
    border-radius: 14px;
}

.header-box {
    padding: 8px 12px;
    background-color: alpha(@mantle, 0.4);
    border-radius: 14px 14px 0 0;
}

.player-name { color: @foam; font-size: 12px; font-weight: bold; }
.player-icon { color: @sea; font-size: 14px; }

.player-selector {
    background-color: @surface0;
    border: 1px solid @surface2;
    border-radius: 8px;
    color: @text;
    padding: 2px 8px;
    font-size: 11px;
    min-height: 24px;
}

.now-playing-box { padding: 16px; background-color: alpha(@mantle, 0.6); }

.album-art { border-radius: 10px; border: 1px solid @surface2; }

.art-placeholder {
    border-radius: 10px; border: 1px solid @surface2;
    background-color: @surface0; color: @dim; font-size: 48px;
}

.track-title { color: @text; font-size: 14px; font-weight: bold; }
.track-artist { color: @foam; font-size: 12px; }
.track-album { color: @dim; font-size: 11px; font-style: italic; }

.control-btn {
    background: transparent; border: none; color: @text;
    font-size: 18px; min-width: 40px; min-height: 40px;
    border-radius: 20px; transition: all 0.2s ease;
}
.control-btn:hover { background-color: alpha(@surface1, 0.8); color: @foam; }
.control-btn.play {
    font-size: 22px; background-color: alpha(@sea, 0.2); color: @sea;
    min-width: 48px; min-height: 48px; border-radius: 24px;
}
.control-btn.play:hover { background-color: alpha(@sea, 0.35); }
.control-btn.active { color: @foam; background-color: alpha(@foam, 0.15); }

.progress-event-box:hover .progress-fill { background-color: @foam; }
.time-label { color: @dim; font-size: 11px; }
.no-player-label { color: @dim; font-size: 13px; }

.tab-btn {
    background: transparent; border: none; color: @dim;
    font-size: 11px; padding: 4px 12px; border-radius: 6px;
    font-weight: bold; min-height: 28px;
}
.tab-btn:hover { color: @text; background-color: alpha(@surface1, 0.5); }
.tab-btn.active-tab { color: @sea; background-color: alpha(@sea, 0.12); }

.search-entry {
    background-color: @surface0; border: 1px solid @surface2;
    border-radius: 8px; color: @text; padding: 4px 10px;
    font-size: 12px; min-height: 28px;
}
.search-entry:focus { border-color: @sea; }

.queue-row { padding: 4px 8px; }
.queue-row:hover { background-color: alpha(@surface1, 0.6); }

.queue-row-playing { background-color: alpha(@sea, 0.1); }
.queue-track { color: @text; font-size: 12px; }
.queue-artist { color: @dim; font-size: 11px; }
.queue-num { color: @dim; font-size: 11px; font-family: monospace; min-width: 24px; }
.queue-duration { color: @dim; font-size: 11px; }

.playlist-row { padding: 6px 10px; }
.playlist-row:hover { background-color: alpha(@surface1, 0.6); }
.playlist-name { color: @text; font-size: 12px; }
.playlist-active { color: @sea; font-weight: bold; }

.quality-badge {
    font-size: 10px;
    font-family: "JetBrains Mono Nerd Font", monospace;
    font-weight: bold;
    color: @sand;
    background-color: alpha(@sand, 0.12);
    border-radius: 4px;
    padding: 1px 6px;
    margin-top: 4px;
}

.quality-hires { color: @foam; background-color: alpha(@foam, 0.12); }

.cold-start-box { padding: 24px; }
.cold-start-btn {
    background-color: alpha(@sea, 0.2); color: @sea;
    border: 1px solid alpha(@sea, 0.3); border-radius: 10px;
    font-size: 14px; padding: 12px 20px;
}
.cold-start-btn:hover { background-color: alpha(@sea, 0.35); }

.header-btn {
    background: transparent; border: none; color: @dim;
    font-size: 13px; min-width: 28px; min-height: 28px;
    border-radius: 14px; padding: 0;
}
.header-btn:hover { color: @text; background-color: alpha(@surface1, 0.6); }

scrolledwindow { background: transparent; }
scrollbar slider { background-color: @surface2; border-radius: 4px; min-width: 4px; }
"""


def get_players():
    try:
        out = subprocess.check_output(
            ["playerctl", "--list-all"], stderr=subprocess.DEVNULL
        ).decode().strip()
        return [p.strip() for p in out.split("\n") if p.strip()] if out else []
    except Exception:
        return []


def get_player_status(player):
    """Get player status: Playing, Paused, or Stopped."""
    try:
        return subprocess.check_output(
            ["playerctl", "-p", player, "status"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "Stopped"


# Priority: dedicated music apps first, then media players, then browsers last.
# Within same priority, Playing > Paused > Stopped.
PLAYER_PRIORITY = {
    "strawberry": 0, "spotify": 0, "cmus": 0, "rhythmbox": 0,
    "audacious": 0, "clementine": 0, "elisa": 0, "tidal": 0,
    "vlc": 1, "mpv": 1, "celluloid": 1, "totem": 1,
    "firefox": 2, "chromium": 2, "chrome": 2, "brave": 2,
}

STATUS_PRIORITY = {"Playing": 0, "Paused": 1, "Stopped": 2}


def pick_best_player(players):
    """Choose the best player: prefer Playing status, then music apps over browsers."""
    if not players:
        return None
    statuses = {p: get_player_status(p) for p in players}

    def sort_key(p):
        name_lower = p.lower()
        # Match against known player names
        app_prio = 3  # unknown defaults to browser-level
        for prefix, prio in PLAYER_PRIORITY.items():
            if prefix in name_lower:
                app_prio = prio
                break
        status_prio = STATUS_PRIORITY.get(statuses.get(p, "Stopped"), 2)
        return (status_prio, app_prio)

    return min(players, key=sort_key)


def playerctl_cmd(player, *args):
    try:
        return subprocess.check_output(
            ["playerctl", "-p", player] + list(args),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return ""


def get_player_icon(name):
    lower = name.lower()
    for key, icon in PLAYER_ICONS.items():
        if key in lower:
            return icon
    return "󰎆"


def format_time(seconds):
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def get_cached_art(url):
    if not url:
        return None
    if url.startswith("file://"):
        path = url[7:]
        return path if os.path.exists(path) else None
    if url.startswith("/") and os.path.exists(url):
        return url
    h = hashlib.md5(url.encode()).hexdigest()
    ext = "png" if ".png" in url.lower() else "jpg"
    path = os.path.join(CACHE_DIR, f"{h}.{ext}")
    if os.path.exists(path):
        return path
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Costa-Music/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read()
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception:
        return None


def get_stream_quality(player_name="strawberry"):
    """Get audio stream quality from PipeWire for a given player."""
    try:
        out = subprocess.check_output(["pw-dump"], stderr=subprocess.DEVNULL,
                                       timeout=3).decode()
        data = json.loads(out)
        for obj in data:
            info = obj.get("info", {})
            props = info.get("props", {})
            name = (props.get("application.name", "") or
                    props.get("node.name", ""))
            if player_name.lower() not in name.lower():
                continue
            fmt_list = info.get("params", {}).get("Format", [])
            for fmt in fmt_list:
                if fmt.get("mediaType") == "audio" and fmt.get("mediaSubtype") == "raw":
                    rate = fmt.get("rate", 0)
                    channels = fmt.get("channels", 0)
                    audio_fmt = fmt.get("format", "")
                    # Parse bit depth from format string (S16LE, S24_32LE, S32LE, F32LE)
                    bits = 16
                    if "S24" in audio_fmt or "24" in audio_fmt:
                        bits = 24
                    elif "S32" in audio_fmt or "F32" in audio_fmt:
                        bits = 32
                    return {"rate": rate, "bits": bits, "channels": channels,
                            "format": audio_fmt}
    except Exception:
        pass
    return None


def format_quality(q):
    """Format quality dict into a display string."""
    if not q:
        return None
    rate_khz = q["rate"] / 1000
    # Format nicely: 44.1kHz, 48kHz, 96kHz, etc.
    if rate_khz == int(rate_khz):
        rate_str = f"{int(rate_khz)}kHz"
    else:
        rate_str = f"{rate_khz:.1f}kHz"
    return f"{q['bits']}bit / {rate_str}"


def is_hires(q):
    """Check if quality is hi-res (>16bit or >48kHz)."""
    if not q:
        return False
    return q["bits"] > 16 or q["rate"] > 48000


def is_strawberry_running():
    try:
        out = subprocess.check_output(["pgrep", "-x", "strawberry"],
                                       stderr=subprocess.DEVNULL).decode().strip()
        return bool(out)
    except Exception:
        return False


def strawberry_is_player(players):
    return any("strawberry" in p.lower() for p in players)


def query_strawberry_db(query_sql, params=()):
    """Query Strawberry's SQLite database."""
    if not os.path.exists(STRAWBERRY_DB):
        return []
    try:
        conn = sqlite3.connect(f"file:{STRAWBERRY_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query_sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_strawberry_playlists():
    """Get playlists via D-Bus."""
    try:
        out = subprocess.check_output([
            "dbus-send", "--print-reply", "--type=method_call",
            "--dest=org.mpris.MediaPlayer2.strawberry",
            "/org/mpris/MediaPlayer2",
            "org.mpris.MediaPlayer2.Playlists.GetPlaylists",
            "uint32:0", "uint32:100", "string:Alphabetical", "boolean:false"
        ], stderr=subprocess.DEVNULL).decode()

        playlists = []
        lines = out.split("\n")
        i = 0
        while i < len(lines):
            if "object path" in lines[i]:
                path = lines[i].split('"')[1] if '"' in lines[i] else ""
                name = lines[i + 1].split('"')[1] if i + 1 < len(lines) and '"' in lines[i + 1] else ""
                if name:
                    playlists.append({"path": path, "name": name})
                i += 3
            else:
                i += 1
        return playlists
    except Exception:
        return []


def activate_strawberry_playlist(playlist_path):
    """Activate a playlist via D-Bus."""
    try:
        subprocess.run([
            "dbus-send", "--type=method_call",
            "--dest=org.mpris.MediaPlayer2.strawberry",
            "/org/mpris/MediaPlayer2",
            "org.mpris.MediaPlayer2.Playlists.ActivatePlaylist",
            f"objpath:{playlist_path}"
        ], capture_output=True, timeout=5)
    except Exception:
        pass


class MusicWidget(Gtk.Window):
    def __init__(self):
        super().__init__(title="Costa Music")
        self.set_default_size(WIDGET_WIDTH, WIDGET_HEIGHT)
        self.set_resizable(False)
        self.set_decorated(False)

        self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)

        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self.current_player = None
        self.players = []
        self.shuffle_on = False
        self.current_art_url = None
        self.current_track_title = ""
        self.current_quality = None
        self.queue_tracks = []
        self.active_tab = "queue"

        self.connect("key-press-event", self.on_key)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.main_box)

        self.build_header()
        self.build_now_playing()
        self.build_controls()
        self.build_tabs()

        self.refresh_players()
        self.update_metadata()
        GLib.timeout_add(1500, self._update_quality)
        GLib.timeout_add(1000, self.update_metadata)
        GLib.timeout_add(5000, self.refresh_players)

        self.show_all()

    # ── Header ──

    def build_header(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.get_style_context().add_class("header-box")

        self.player_icon_label = Gtk.Label(label="󰎆")
        self.player_icon_label.get_style_context().add_class("player-icon")
        box.pack_start(self.player_icon_label, False, False, 0)

        self.player_name_label = Gtk.Label(label="No Player")
        self.player_name_label.get_style_context().add_class("player-name")
        box.pack_start(self.player_name_label, False, False, 0)

        box.pack_start(Gtk.Box(), True, True, 0)

        # Hide Strawberry button
        self.hide_btn = Gtk.Button(label="󰘑")
        self.hide_btn.set_tooltip_text("Hide Strawberry")
        self.hide_btn.get_style_context().add_class("header-btn")
        self.hide_btn.connect("clicked", self.on_hide_strawberry)
        box.pack_end(self.hide_btn, False, False, 0)

        # Player selector
        self.player_combo = Gtk.ComboBoxText()
        self.player_combo.get_style_context().add_class("player-selector")
        self.player_combo.connect("changed", self.on_player_selected)
        box.pack_end(self.player_combo, False, False, 4)

        self.main_box.pack_start(box, False, False, 0)

    # ── Now Playing ──

    def build_now_playing(self):
        # Cold start overlay (shown when no player)
        self.cold_start_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.cold_start_box.get_style_context().add_class("cold-start-box")
        self.cold_start_box.set_valign(Gtk.Align.CENTER)
        self.cold_start_box.set_halign(Gtk.Align.CENTER)

        icon_lbl = Gtk.Label(label="󰎆")
        icon_lbl.set_markup("<span size='48000' color='#5b94a8'>󰎆</span>")
        self.cold_start_box.pack_start(icon_lbl, False, False, 0)

        start_btn = Gtk.Button(label="  Start Music")
        start_btn.get_style_context().add_class("cold-start-btn")
        start_btn.connect("clicked", self.on_cold_start)
        self.cold_start_box.pack_start(start_btn, False, False, 0)

        hint = Gtk.Label(label="Launch Strawberry and play")
        hint.get_style_context().add_class("no-player-label")
        self.cold_start_box.pack_start(hint, False, False, 0)

        # Normal now-playing
        self.np_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.np_box.get_style_context().add_class("now-playing-box")

        self.art_image = Gtk.Image()
        self.art_image.set_size_request(ART_SIZE, ART_SIZE)
        self.art_image.get_style_context().add_class("album-art")

        self.art_placeholder = Gtk.Label(label="󰎆")
        self.art_placeholder.set_size_request(ART_SIZE, ART_SIZE)
        self.art_placeholder.get_style_context().add_class("art-placeholder")
        self.art_placeholder.set_valign(Gtk.Align.CENTER)
        self.art_placeholder.set_halign(Gtk.Align.CENTER)

        self.art_stack = Gtk.Stack()
        self.art_stack.add_named(self.art_placeholder, "placeholder")
        self.art_stack.add_named(self.art_image, "art")
        self.art_stack.set_visible_child_name("placeholder")
        self.np_box.pack_start(self.art_stack, False, False, 0)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        info_box.set_valign(Gtk.Align.CENTER)

        self.title_label = Gtk.Label(label="Not Playing")
        self.title_label.set_xalign(0)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.set_max_width_chars(20)
        self.title_label.get_style_context().add_class("track-title")
        info_box.pack_start(self.title_label, False, False, 0)

        self.artist_label = Gtk.Label()
        self.artist_label.set_xalign(0)
        self.artist_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.artist_label.set_max_width_chars(20)
        self.artist_label.get_style_context().add_class("track-artist")
        info_box.pack_start(self.artist_label, False, False, 0)

        self.album_label = Gtk.Label()
        self.album_label.set_xalign(0)
        self.album_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.album_label.set_max_width_chars(20)
        self.album_label.get_style_context().add_class("track-album")
        info_box.pack_start(self.album_label, False, False, 0)

        self.quality_label = Gtk.Label()
        self.quality_label.set_xalign(0)
        self.quality_label.get_style_context().add_class("quality-badge")
        self.quality_label.set_no_show_all(True)
        info_box.pack_start(self.quality_label, False, False, 0)

        self.np_box.pack_start(info_box, True, True, 0)

        # Stack: cold start vs now playing
        self.main_stack = Gtk.Stack()
        self.main_stack.add_named(self.cold_start_box, "cold")
        self.main_stack.add_named(self.np_box, "playing")
        # Show all children of both stack pages so they're ready when switched
        self.cold_start_box.show_all()
        self.np_box.show_all()
        self.main_stack.set_visible_child_name("cold")

        self.main_box.pack_start(self.main_stack, False, False, 0)

    # ── Controls ──

    def build_controls(self):
        self.ctrl_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.ctrl_box.set_margin_start(16)
        self.ctrl_box.set_margin_end(16)
        self.ctrl_box.set_margin_top(6)
        self.ctrl_box.set_margin_bottom(2)

        prog_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.time_current = Gtk.Label(label="0:00")
        self.time_current.get_style_context().add_class("time-label")
        prog_box.pack_start(self.time_current, False, False, 0)

        self.progress_event = Gtk.EventBox()
        self.progress_event.set_hexpand(True)
        self.progress_event.get_style_context().add_class("progress-event-box")
        self.progress_event.connect("button-press-event", self.on_seek)

        self.progress_drawing = Gtk.DrawingArea()
        self.progress_drawing.set_size_request(-1, 6)
        self.progress_drawing.connect("draw", self.on_draw_progress)
        self.progress_event.add(self.progress_drawing)

        self.progress_fraction = 0.0
        self.track_length_s = 0.0

        prog_box.pack_start(self.progress_event, True, True, 0)

        self.time_total = Gtk.Label(label="0:00")
        self.time_total.get_style_context().add_class("time-label")
        prog_box.pack_start(self.time_total, False, False, 0)

        self.ctrl_box.pack_start(prog_box, False, False, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        btn_box.set_halign(Gtk.Align.CENTER)

        self.shuffle_btn = self._make_btn("󰒝", "control-btn", self.on_shuffle)
        btn_box.pack_start(self.shuffle_btn, False, False, 0)

        prev_btn = self._make_btn("󰒮", "control-btn", self.on_prev)
        btn_box.pack_start(prev_btn, False, False, 0)

        self.play_btn = self._make_btn("", "control-btn play", self.on_play_pause)
        btn_box.pack_start(self.play_btn, False, False, 0)

        next_btn = self._make_btn("󰒭", "control-btn", self.on_next)
        btn_box.pack_start(next_btn, False, False, 0)

        # Repeat button (replaces the old spacer)
        self.repeat_btn = self._make_btn("󰑖", "control-btn", self.on_repeat)
        btn_box.pack_start(self.repeat_btn, False, False, 0)

        self.ctrl_box.pack_start(btn_box, False, False, 0)
        self.main_box.pack_start(self.ctrl_box, False, False, 0)

    # ── Tabs: Queue / Search / Playlists ──

    def build_tabs(self):
        tab_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        tab_bar.set_margin_start(12)
        tab_bar.set_margin_end(12)
        tab_bar.set_margin_top(4)

        self.tab_buttons = {}
        for tab_id, label in [("queue", "Queue"), ("search", "Search"),
                                ("playlists", "Playlists"), ("players", "Players")]:
            btn = Gtk.Button(label=label)
            btn.get_style_context().add_class("tab-btn")
            btn.connect("clicked", self.on_tab_clicked, tab_id)
            tab_bar.pack_start(btn, True, True, 0)
            self.tab_buttons[tab_id] = btn

        self.main_box.pack_start(tab_bar, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_start(12)
        sep.set_margin_end(12)
        self.main_box.pack_start(sep, False, False, 2)

        # Tab content stack
        self.tab_stack = Gtk.Stack()
        self.tab_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.tab_stack.set_transition_duration(150)

        self.tab_stack.add_named(self._build_queue_tab(), "queue")
        self.tab_stack.add_named(self._build_search_tab(), "search")
        self.tab_stack.add_named(self._build_playlists_tab(), "playlists")
        self.tab_stack.add_named(self._build_players_tab(), "players")

        self.main_box.pack_start(self.tab_stack, True, True, 0)

        # Set initial active tab
        self._set_active_tab("queue")

    def _build_queue_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.queue_listbox = Gtk.ListBox()
        self.queue_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.queue_listbox.connect("row-activated", self.on_queue_row_clicked)
        scroll.add(self.queue_listbox)
        box.pack_start(scroll, True, True, 0)
        return box

    def _build_search_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(6)

        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text("Search tracks, artists, albums...")
        self.search_entry.get_style_context().add_class("search-entry")
        self.search_entry.connect("changed", self.on_search_changed)
        self.search_entry.connect("activate", self.on_search_activate)
        box.pack_start(self.search_entry, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.search_listbox = Gtk.ListBox()
        self.search_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.search_listbox.connect("row-activated", self.on_search_row_clicked)
        scroll.add(self.search_listbox)
        box.pack_start(scroll, True, True, 0)
        return box

    def _build_playlists_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.playlist_listbox = Gtk.ListBox()
        self.playlist_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.playlist_listbox.connect("row-activated", self.on_playlist_row_clicked)
        scroll.add(self.playlist_listbox)
        box.pack_start(scroll, True, True, 0)
        return box

    def _build_players_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.player_listbox = Gtk.ListBox()
        self.player_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.player_listbox.connect("row-activated", self.on_player_row_clicked)
        scroll.add(self.player_listbox)
        box.pack_start(scroll, True, True, 0)
        return box

    def _set_active_tab(self, tab_id):
        self.active_tab = tab_id
        self.tab_stack.set_visible_child_name(tab_id)
        for tid, btn in self.tab_buttons.items():
            ctx = btn.get_style_context()
            if tid == tab_id:
                ctx.add_class("active-tab")
            else:
                ctx.remove_class("active-tab")

        if tab_id == "queue":
            self._refresh_queue()
        elif tab_id == "playlists":
            self._refresh_playlists()
        elif tab_id == "players":
            self._rebuild_player_list()

    def on_tab_clicked(self, btn, tab_id):
        self._set_active_tab(tab_id)

    def _make_btn(self, label, css_class, callback):
        btn = Gtk.Button(label=label)
        for cls in css_class.split():
            btn.get_style_context().add_class(cls)
        if callback:
            btn.connect("clicked", callback)
        return btn

    # ── Queue ──

    def _refresh_queue(self):
        for child in self.queue_listbox.get_children():
            self.queue_listbox.remove(child)

        tracks = query_strawberry_db(
            "SELECT rowid, title, artist, album, length, art_automatic "
            "FROM playlist_items ORDER BY rowid")
        self.queue_tracks = tracks

        if not tracks:
            lbl = Gtk.Label(label="No tracks in playlist")
            lbl.get_style_context().add_class("no-player-label")
            lbl.set_margin_top(16)
            row = Gtk.ListBoxRow()
            row.add(lbl)
            self.queue_listbox.add(row)
        else:
            for i, t in enumerate(tracks):
                row = Gtk.ListBoxRow()
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                hbox.get_style_context().add_class("queue-row")

                # Highlight current track
                if t["title"] == self.current_track_title:
                    hbox.get_style_context().add_class("queue-row-playing")

                num = Gtk.Label(label=f"{i + 1}")
                num.get_style_context().add_class("queue-num")
                num.set_xalign(1)
                hbox.pack_start(num, False, False, 0)

                info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
                title_lbl = Gtk.Label(label=t["title"] or "Unknown")
                title_lbl.set_xalign(0)
                title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                title_lbl.set_max_width_chars(30)
                title_lbl.get_style_context().add_class("queue-track")
                info.pack_start(title_lbl, False, False, 0)

                artist_lbl = Gtk.Label(label=t["artist"] or "")
                artist_lbl.set_xalign(0)
                artist_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                artist_lbl.set_max_width_chars(30)
                artist_lbl.get_style_context().add_class("queue-artist")
                info.pack_start(artist_lbl, False, False, 0)

                hbox.pack_start(info, True, True, 0)

                if t.get("length") and t["length"] > 0:
                    dur_s = t["length"] / 1_000_000_000
                    dur_lbl = Gtk.Label(label=format_time(dur_s))
                    dur_lbl.get_style_context().add_class("queue-duration")
                    hbox.pack_end(dur_lbl, False, False, 0)

                row.add(hbox)
                self.queue_listbox.add(row)

        self.queue_listbox.show_all()

    def on_queue_row_clicked(self, listbox, row):
        idx = row.get_index()
        if 0 <= idx < len(self.queue_tracks):
            # strawberry --play-track is 1-indexed
            subprocess.Popen(["strawberry", "--play-track", str(idx + 1)],
                             start_new_session=True)
            GLib.timeout_add(500, self.update_metadata)
            GLib.timeout_add(500, self._refresh_queue)

    # ── Search ──

    def on_search_changed(self, entry):
        # Debounce: use a short timeout
        if hasattr(self, '_search_timeout'):
            GLib.source_remove(self._search_timeout)
        self._search_timeout = GLib.timeout_add(300, self._do_search)

    def on_search_activate(self, entry):
        self._do_search()

    def _do_search(self):
        query = self.search_entry.get_text().strip()
        for child in self.search_listbox.get_children():
            self.search_listbox.remove(child)

        if len(query) < 2:
            if query:
                lbl = Gtk.Label(label="Type at least 2 characters")
                lbl.get_style_context().add_class("no-player-label")
                lbl.set_margin_top(12)
                row = Gtk.ListBoxRow()
                row.add(lbl)
                self.search_listbox.add(row)
                self.search_listbox.show_all()
            return False

        pattern = f"%{query}%"
        results = query_strawberry_db(
            "SELECT rowid, title, artist, album, length "
            "FROM playlist_items "
            "WHERE title LIKE ? OR artist LIKE ? OR album LIKE ? "
            "ORDER BY artist, album, rowid LIMIT 50",
            (pattern, pattern, pattern))

        if not results:
            lbl = Gtk.Label(label=f'No results for "{query}"')
            lbl.get_style_context().add_class("no-player-label")
            lbl.set_margin_top(12)
            row = Gtk.ListBoxRow()
            row.add(lbl)
            self.search_listbox.add(row)
        else:
            for r in results:
                row = Gtk.ListBoxRow()
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                hbox.get_style_context().add_class("queue-row")

                info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
                title_lbl = Gtk.Label(label=r["title"] or "Unknown")
                title_lbl.set_xalign(0)
                title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                title_lbl.set_max_width_chars(30)
                title_lbl.get_style_context().add_class("queue-track")
                info.pack_start(title_lbl, False, False, 0)

                sub = f"{r['artist'] or ''}"
                if r.get("album"):
                    sub += f" — {r['album']}"
                sub_lbl = Gtk.Label(label=sub)
                sub_lbl.set_xalign(0)
                sub_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                sub_lbl.set_max_width_chars(35)
                sub_lbl.get_style_context().add_class("queue-artist")
                info.pack_start(sub_lbl, False, False, 0)

                hbox.pack_start(info, True, True, 0)

                if r.get("length") and r["length"] > 0:
                    dur_s = r["length"] / 1_000_000_000
                    dur_lbl = Gtk.Label(label=format_time(dur_s))
                    dur_lbl.get_style_context().add_class("queue-duration")
                    hbox.pack_end(dur_lbl, False, False, 0)

                row.add(hbox)
                row._rowid = r["rowid"]
                self.search_listbox.add(row)

        self.search_listbox.show_all()
        return False

    def on_search_row_clicked(self, listbox, row):
        if hasattr(row, '_rowid'):
            # Find position in playlist_items by rowid
            rowid = row._rowid
            tracks = query_strawberry_db(
                "SELECT rowid FROM playlist_items ORDER BY rowid")
            for i, t in enumerate(tracks):
                if t["rowid"] == rowid:
                    subprocess.Popen(["strawberry", "--play-track", str(i + 1)],
                                     start_new_session=True)
                    GLib.timeout_add(500, self.update_metadata)
                    self._set_active_tab("queue")
                    break

    # ── Playlists ──

    def _refresh_playlists(self):
        for child in self.playlist_listbox.get_children():
            self.playlist_listbox.remove(child)

        playlists = get_strawberry_playlists()

        if not playlists:
            lbl = Gtk.Label(label="No playlists found")
            lbl.get_style_context().add_class("no-player-label")
            lbl.set_margin_top(16)
            row = Gtk.ListBoxRow()
            row.add(lbl)
            self.playlist_listbox.add(row)
        else:
            for pl in playlists:
                row = Gtk.ListBoxRow()
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                hbox.get_style_context().add_class("playlist-row")

                icon = Gtk.Label(label="󰲸")
                icon.get_style_context().add_class("player-icon")
                hbox.pack_start(icon, False, False, 0)

                name = Gtk.Label(label=pl["name"])
                name.set_xalign(0)
                name.get_style_context().add_class("playlist-name")
                hbox.pack_start(name, True, True, 0)

                play_btn = Gtk.Button(label="")
                play_btn.get_style_context().add_class("header-btn")
                play_btn.connect("clicked", self._on_play_playlist, pl["path"])
                hbox.pack_end(play_btn, False, False, 0)

                row.add(hbox)
                row._playlist_path = pl["path"]
                self.playlist_listbox.add(row)

        self.playlist_listbox.show_all()

    def on_playlist_row_clicked(self, listbox, row):
        if hasattr(row, '_playlist_path'):
            self._on_play_playlist(None, row._playlist_path)

    def _on_play_playlist(self, btn, path):
        activate_strawberry_playlist(path)
        # Start playback
        GLib.timeout_add(300, lambda: (
            subprocess.Popen(["strawberry", "--play"],
                             start_new_session=True),
            False
        )[-1])
        GLib.timeout_add(800, self.update_metadata)
        GLib.timeout_add(1000, self._refresh_queue)

    # ── Players tab ──

    def _rebuild_player_list(self):
        for child in self.player_listbox.get_children():
            self.player_listbox.remove(child)

        if not self.players:
            lbl = Gtk.Label(label="No MPRIS players detected")
            lbl.get_style_context().add_class("no-player-label")
            lbl.set_margin_top(16)
            row = Gtk.ListBoxRow()
            row.add(lbl)
            self.player_listbox.add(row)
        else:
            for p in self.players:
                row = Gtk.ListBoxRow()
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                hbox.set_margin_top(4)
                hbox.set_margin_bottom(4)
                hbox.set_margin_start(8)
                hbox.set_margin_end(8)

                icon = Gtk.Label(label=get_player_icon(p))
                icon.get_style_context().add_class("player-icon")
                hbox.pack_start(icon, False, False, 0)

                name = Gtk.Label(label=p)
                name.set_xalign(0)
                name.get_style_context().add_class("queue-track")
                hbox.pack_start(name, True, True, 0)

                status = playerctl_cmd(p, "status")
                status_lbl = Gtk.Label(label=status or "Stopped")
                status_lbl.get_style_context().add_class("time-label")
                hbox.pack_end(status_lbl, False, False, 0)

                row.add(hbox)
                self.player_listbox.add(row)

        self.player_listbox.show_all()

    def on_player_row_clicked(self, listbox, row):
        idx = row.get_index()
        if 0 <= idx < len(self.players):
            self.current_player = self.players[idx]
            self.player_combo.set_active(idx)
            self.current_art_url = None
            self.update_metadata()

    # ── Progress drawing ──

    def on_draw_progress(self, widget, cr):
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        cr.set_source_rgba(0.184, 0.2, 0.271, 1)
        cr.rectangle(0, 0, w, h)
        cr.fill()
        if self.progress_fraction > 0:
            cr.set_source_rgba(0.357, 0.58, 0.659, 1)
            cr.rectangle(0, 0, w * self.progress_fraction, h)
            cr.fill()

    def on_seek(self, widget, event):
        if not self.current_player or self.track_length_s <= 0:
            return
        alloc = widget.get_allocation()
        fraction = max(0.0, min(1.0, event.x / alloc.width))
        target_s = fraction * self.track_length_s
        playerctl_cmd(self.current_player, "position", str(target_s))
        self.progress_fraction = fraction
        self.progress_drawing.queue_draw()

    # ── Events ──

    def on_key(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()

    def on_cold_start(self, btn):
        """Launch Strawberry and start playing."""
        if not is_strawberry_running():
            subprocess.Popen(["strawberry"], start_new_session=True)
            # Wait for it to start, then play
            GLib.timeout_add(2000, self._cold_start_play)
        else:
            subprocess.Popen(["strawberry", "--play"], start_new_session=True)
            GLib.timeout_add(500, self.refresh_players)
            GLib.timeout_add(800, self.update_metadata)

    def _cold_start_play(self):
        subprocess.Popen(["strawberry", "--play"], start_new_session=True)
        # Hide strawberry window after launch
        GLib.timeout_add(1000, self._hide_strawberry_window)
        GLib.timeout_add(500, self._select_strawberry_player)
        GLib.timeout_add(1500, self._select_strawberry_player)
        GLib.timeout_add(2000, self._refresh_queue)
        return False

    def _select_strawberry_player(self):
        """After cold-start, force-select Strawberry once it appears."""
        self.players = get_players()
        self._rebuild_player_combo()
        for p in self.players:
            if "strawberry" in p.lower():
                self.current_player = p
                self.player_combo.set_active(self.players.index(p))
                self.current_art_url = None
                self.update_metadata()
                return False
        # Strawberry not yet registered — refresh_players will pick it up
        return False

    def on_hide_strawberry(self, btn):
        self._toggle_strawberry_window()

    def _toggle_strawberry_window(self):
        """Toggle Strawberry between special:music (hidden) and current workspace."""
        try:
            out = subprocess.check_output(
                ["hyprctl", "clients", "-j"], timeout=3).decode()
            import json as _json
            clients = _json.loads(out)
            for c in clients:
                if "strawberry" in c.get("class", "").lower():
                    ws = c.get("workspace", {}).get("name", "")
                    if ws.startswith("special:"):
                        # It's hidden — bring to current workspace
                        subprocess.run(
                            ["hyprctl", "dispatch", "movetoworkspace",
                             f"e+0,class:org.strawberrymusicplayer.strawberry"],
                            capture_output=True)
                        self.hide_btn.set_label("󰘑")
                        self.hide_btn.set_tooltip_text("Hide Strawberry")
                    else:
                        # It's visible — hide it
                        subprocess.run(
                            ["hyprctl", "dispatch", "movetoworkspacesilent",
                             "special:music,class:org.strawberrymusicplayer.strawberry"],
                            capture_output=True)
                        self.hide_btn.set_label("󰈈")
                        self.hide_btn.set_tooltip_text("Show Strawberry")
                    return False
        except Exception:
            pass
        return False

    def _hide_strawberry_window(self):
        subprocess.run(
            ["hyprctl", "dispatch", "movetoworkspacesilent",
             "special:music,class:org.strawberrymusicplayer.strawberry"],
            capture_output=True)
        self.hide_btn.set_label("󰈈")
        self.hide_btn.set_tooltip_text("Show Strawberry")
        return False

    def on_play_pause(self, btn):
        if not self.current_player:
            self.on_cold_start(btn)
            return
        playerctl_cmd(self.current_player, "play-pause")
        GLib.timeout_add(100, self.update_metadata)

    def on_next(self, btn):
        if self.current_player:
            playerctl_cmd(self.current_player, "next")
            GLib.timeout_add(300, self.update_metadata)
            GLib.timeout_add(500, self._refresh_queue)

    def on_prev(self, btn):
        if self.current_player:
            playerctl_cmd(self.current_player, "previous")
            GLib.timeout_add(300, self.update_metadata)
            GLib.timeout_add(500, self._refresh_queue)

    def on_shuffle(self, btn):
        if not self.current_player:
            return
        self.shuffle_on = not self.shuffle_on
        playerctl_cmd(self.current_player, "shuffle", "On" if self.shuffle_on else "Off")
        ctx = self.shuffle_btn.get_style_context()
        if self.shuffle_on:
            ctx.add_class("active")
        else:
            ctx.remove_class("active")

    def on_repeat(self, btn):
        if not self.current_player:
            return
        loop = playerctl_cmd(self.current_player, "loop")
        # Cycle: None -> Playlist -> Track -> None
        next_loop = {"None": "Playlist", "Playlist": "Track", "Track": "None"}.get(loop, "None")
        playerctl_cmd(self.current_player, "loop", next_loop)
        ctx = self.repeat_btn.get_style_context()
        if next_loop != "None":
            ctx.add_class("active")
            self.repeat_btn.set_label("󰑘" if next_loop == "Track" else "󰑖")
        else:
            ctx.remove_class("active")
            self.repeat_btn.set_label("󰑖")

    def _update_quality(self):
        """Fetch audio stream quality from PipeWire."""
        player_name = self.current_player or "strawberry"
        # Extract base player name (e.g. "strawberry" from "strawberry.instance12345")
        base = player_name.split(".")[0]
        q = get_stream_quality(base)
        self.current_quality = q
        q_str = format_quality(q)
        if q_str:
            self.quality_label.set_text(q_str)
            ctx = self.quality_label.get_style_context()
            if is_hires(q):
                ctx.add_class("quality-hires")
            else:
                ctx.remove_class("quality-hires")
            self.quality_label.show()
        else:
            self.quality_label.hide()
        return False  # don't repeat

    def on_player_selected(self, combo):
        text = combo.get_active_text()
        if text and text in self.players:
            self.current_player = text
            self.current_art_url = None
            self.update_metadata()

    # ── Player detection ──

    def refresh_players(self):
        new_players = get_players()
        if new_players != self.players:
            self.players = new_players
            self._rebuild_player_combo()
            if self.active_tab == "players":
                self._rebuild_player_list()

            if self.current_player not in self.players:
                best = pick_best_player(self.players)
                self.current_player = best
                if best and best in self.players:
                    self.player_combo.set_active(self.players.index(best))
                self.current_art_url = None
        else:
            # Even if player list unchanged, re-evaluate best player
            # so that a newly-playing player takes priority over a paused one
            # (only auto-switch if current player is NOT playing)
            if self.current_player and self.players:
                cur_status = get_player_status(self.current_player)
                if cur_status != "Playing":
                    best = pick_best_player(self.players)
                    if best and best != self.current_player:
                        best_status = get_player_status(best)
                        if best_status == "Playing":
                            self.current_player = best
                            self.player_combo.set_active(self.players.index(best))
                            self.current_art_url = None

        # Show/hide cold start — show cold start if no player is actively
        # playing or paused (i.e. all are stopped/absent)
        has_active = False
        if self.current_player:
            cur_status = get_player_status(self.current_player)
            has_active = cur_status in ("Playing", "Paused")

        if has_active:
            self.main_stack.set_visible_child_name("playing")
            self.ctrl_box.set_visible(True)
        else:
            self.main_stack.set_visible_child_name("cold")
            self.ctrl_box.set_visible(False)

        return True

    def _rebuild_player_combo(self):
        self.player_combo.remove_all()
        for p in self.players:
            self.player_combo.append_text(p)
        if self.current_player in self.players:
            self.player_combo.set_active(self.players.index(self.current_player))
        elif self.players:
            self.player_combo.set_active(0)

    # ── Metadata polling ──

    def update_metadata(self):
        if not self.current_player:
            self.title_label.set_text("Not Playing")
            self.artist_label.set_text("")
            self.album_label.set_text("")
            self.player_name_label.set_text("No Player")
            self.player_icon_label.set_text("󰎆")
            self.play_btn.set_label("")
            self.progress_fraction = 0
            self.progress_drawing.queue_draw()
            self.time_current.set_text("0:00")
            self.time_total.set_text("0:00")
            self.art_stack.set_visible_child_name("placeholder")
            return True

        p = self.current_player
        self.player_name_label.set_text(p)
        self.player_icon_label.set_text(get_player_icon(p))

        # Show/hide the hide button (only relevant for Strawberry)
        self.hide_btn.set_visible("strawberry" in p.lower())

        status = playerctl_cmd(p, "status")

        if not status or status == "Stopped":
            self.title_label.set_text("Not Playing")
            self.artist_label.set_text("")
            self.album_label.set_text("")
            self.play_btn.set_label("")
            self.progress_fraction = 0
            self.progress_drawing.queue_draw()
            self.time_current.set_text("0:00")
            self.time_total.set_text("0:00")
            return True

        self.main_stack.set_visible_child_name("playing")
        self.ctrl_box.set_visible(True)

        title = playerctl_cmd(p, "metadata", "title")
        artist = playerctl_cmd(p, "metadata", "artist")
        album = playerctl_cmd(p, "metadata", "album")
        art_url = playerctl_cmd(p, "metadata", "mpris:artUrl")
        length_us = playerctl_cmd(p, "metadata", "mpris:length")
        position = playerctl_cmd(p, "position")

        # Track if current track changed (for queue highlight + quality refresh)
        old_title = self.current_track_title
        self.current_track_title = title or ""
        if old_title != self.current_track_title:
            if self.active_tab == "queue":
                self._refresh_queue()
            # Refresh quality on track change (delay slightly for PipeWire to settle)
            GLib.timeout_add(500, self._update_quality)

        self.title_label.set_text(title or "Unknown Track")
        self.artist_label.set_text(artist or "Unknown Artist")
        self.album_label.set_text(album or "")

        self.play_btn.set_label("󰏤" if status == "Playing" else "")

        if art_url != self.current_art_url:
            self.current_art_url = art_url
            art_path = get_cached_art(art_url)
            if art_path:
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        art_path, ART_SIZE, ART_SIZE, True)
                    self.art_image.set_from_pixbuf(pixbuf)
                    self.art_stack.set_visible_child_name("art")
                except Exception:
                    self.art_stack.set_visible_child_name("placeholder")
            else:
                self.art_stack.set_visible_child_name("placeholder")

        try:
            length_s = int(length_us) / 1_000_000 if length_us else 0
            pos_s = float(position) if position else 0
        except (ValueError, TypeError):
            length_s = 0
            pos_s = 0

        self.track_length_s = length_s

        if length_s > 0:
            self.progress_fraction = min(1.0, pos_s / length_s)
            self.time_current.set_text(format_time(pos_s))
            self.time_total.set_text(format_time(length_s))
        else:
            self.progress_fraction = 0
            self.time_current.set_text(format_time(pos_s) if pos_s > 0 else "0:00")
            self.time_total.set_text("--:--")

        self.progress_drawing.queue_draw()

        shuffle = playerctl_cmd(p, "shuffle")
        self.shuffle_on = shuffle == "On"
        ctx = self.shuffle_btn.get_style_context()
        if self.shuffle_on:
            ctx.add_class("active")
        else:
            ctx.remove_class("active")

        loop = playerctl_cmd(p, "loop")
        ctx = self.repeat_btn.get_style_context()
        if loop and loop != "None":
            ctx.add_class("active")
            self.repeat_btn.set_label("󰑘" if loop == "Track" else "󰑖")
        else:
            ctx.remove_class("active")
            self.repeat_btn.set_label("󰑖")

        return True

    def position_near_waybar(self):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        if monitor:
            geom = monitor.get_geometry()
            self.move(geom.x + 200, geom.y + 44)


def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def read_pid():
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def is_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def cleanup_pid(*_args):
    try:
        os.unlink(PID_FILE)
    except FileNotFoundError:
        pass


def main():
    GLib.set_prgname("costa-music")
    GLib.set_application_name("Costa Music")

    existing = read_pid()
    if existing and existing != os.getpid() and is_running(existing):
        os.kill(existing, signal.SIGTERM)
        cleanup_pid()
        sys.exit(0)

    write_pid()
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())

    win = MusicWidget()
    win.connect("destroy", lambda *_: Gtk.main_quit())
    win.show_all()

    try:
        Gtk.main()
    finally:
        cleanup_pid()


if __name__ == "__main__":
    main()
