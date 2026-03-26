#!/usr/bin/env python3
"""Costa AI Widget — GTK4 dropdown panel for the Waybar AI module.

Shows:
- Active model indicator
- Stop button (visible while query running)
- Last response text
- Usage stats (today's queries, cost, avg latency)
- Report button for bad answers

Launched via toggle-app.sh from Waybar click.
"""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from gi.repository import Gtk, Adw, Gdk, GLib, Pango

# Costa theme colors
COSTA_BG = "#1a1b26"
COSTA_FG = "#c0caf5"
COSTA_SEA = "#7aa2f7"
COSTA_SAND = "#e0af68"
COSTA_FOAM = "#9ece6a"
COSTA_CORAL = "#f7768e"
COSTA_DIM = "#565f89"

CONVERSATION_FILE = "/tmp/costa-conversation.json"
_xdg_model = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "costa/ollama-smart-model"
SMART_MODEL = str(_xdg_model) if _xdg_model.exists() else "/tmp/ollama-smart-model"
PID_FILE = "/tmp/costa-ai.pid"
STATUS_FILE = "/tmp/ptt-voice-status"
OUTPUT_FILE = "/tmp/ptt-voice-output"

# Paths for db access
AI_ROUTER_DIR = Path.home() / "projects" / "costa-os" / "ai-router"
INSTALLED_DIR = Path("/usr/share/costa-os/ai-router")

CSS = f"""
window {{
    background-color: {COSTA_BG};
    border: 2px solid {COSTA_SEA};
    border-radius: 12px;
}}
.widget-title {{
    color: {COSTA_SEA};
    font-size: 16px;
    font-weight: bold;
    font-family: "JetBrainsMono Nerd Font";
}}
.model-label {{
    color: {COSTA_FOAM};
    font-size: 14px;
    font-family: "JetBrainsMono Nerd Font";
}}
.stats-label {{
    color: {COSTA_DIM};
    font-size: 11px;
    font-family: "JetBrainsMono Nerd Font";
}}
.response-text {{
    color: {COSTA_FG};
    font-size: 12px;
    font-family: "JetBrainsMono Nerd Font";
    padding: 8px;
    background-color: rgba(26, 27, 38, 0.8);
    border-radius: 6px;
}}
.query-entry {{
    color: {COSTA_FG};
    font-size: 14px;
    font-family: "JetBrainsMono Nerd Font";
    padding: 8px 12px;
    background-color: rgba(40, 42, 54, 0.9);
    border: 1px solid {COSTA_DIM};
    border-radius: 8px;
    caret-color: {COSTA_SEA};
}}
.query-entry:focus {{
    border-color: {COSTA_SEA};
}}
.send-button {{
    background-color: {COSTA_SEA};
    color: {COSTA_BG};
    border-radius: 8px;
    padding: 4px 14px;
    font-weight: bold;
    font-family: "JetBrainsMono Nerd Font";
}}
.send-button:hover {{
    background-color: {COSTA_FOAM};
}}
.stop-button {{
    background-color: {COSTA_CORAL};
    color: white;
    border-radius: 6px;
    padding: 4px 12px;
    font-weight: bold;
}}
.stop-button:hover {{
    background-color: #ff4060;
}}
.report-button {{
    color: {COSTA_SAND};
    font-size: 12px;
}}
.report-status {{
    color: {COSTA_SEA};
    font-size: 11px;
    font-family: "JetBrainsMono Nerd Font";
    padding: 4px 8px;
    background-color: rgba(122, 162, 247, 0.1);
    border-radius: 6px;
}}
.report-status.done {{
    color: {COSTA_FOAM};
    background-color: rgba(158, 206, 106, 0.1);
}}
.report-status.error {{
    color: {COSTA_CORAL};
    background-color: rgba(247, 118, 142, 0.1);
}}
.separator {{
    background-color: {COSTA_DIM};
    min-height: 1px;
}}
"""


def get_model_name() -> str:
    """Get friendly name of the currently loaded model."""
    try:
        model = Path(SMART_MODEL).read_text().strip()
    except Exception:
        return "No Model"

    model_map = {
        "qwen2.5:14b": "Qwen 14B",
        "qwen2.5:7b": "Qwen 7B",
        "qwen2.5:3b": "Qwen 3B",
        "qwen3:14b": "Qwen3 14B",
        "qwen3:4b": "Qwen3 4B",
        "gemma3:1b": "Gemma 1B",
    }
    for key, name in model_map.items():
        if model.startswith(key):
            return name
    return model or "No Model"


def get_last_response() -> tuple[str, str, str]:
    """Get last conversation entry: (query, response, model)."""
    try:
        data = json.loads(Path(CONVERSATION_FILE).read_text())
        if data:
            last = data[-1]
            return last.get("q", ""), last.get("a", ""), last.get("m", "")
    except Exception:
        pass
    return "", "", ""


def is_query_running() -> bool:
    """Check if a costa-ai query is currently running."""
    try:
        pid = int(Path(PID_FILE).read_text().strip())
        os.kill(pid, 0)  # Check if process exists
        return True
    except Exception:
        return False


def stop_query():
    """Send SIGTERM to running query."""
    try:
        pid = int(Path(PID_FILE).read_text().strip())
        os.kill(pid, 15)  # SIGTERM
    except Exception:
        pass


def get_usage_stats() -> dict:
    """Get today's usage stats from the database."""
    try:
        # Try importing from ai-router
        for path in [AI_ROUTER_DIR, INSTALLED_DIR]:
            if (path / "db.py").exists():
                sys.path.insert(0, str(path))
                from db import get_usage_stats
                return get_usage_stats("today")
    except Exception:
        pass
    return {"total_queries": 0, "total_cost": 0, "avg_latency_ms": 0}


class CostaAIWidget(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.costa.ai-widget")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        # Load CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            app.get_active_window().get_display() if app.get_active_window() else
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Window
        self.win = Gtk.ApplicationWindow(application=app)
        self.win.set_title("dropdown-costa-ai-widget")
        self.win.set_default_size(450, 380)
        self.win.set_resizable(False)

        # Main box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)

        # Header row: title + model + stop button
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        title = Gtk.Label(label="󱜙 Costa")
        title.add_css_class("widget-title")
        title.set_halign(Gtk.Align.START)
        header.append(title)

        header.append(Gtk.Box(hexpand=True))  # spacer

        self.model_label = Gtk.Label(label=get_model_name())
        self.model_label.add_css_class("model-label")
        header.append(self.model_label)

        self.stop_btn = Gtk.Button(label="■ Stop")
        self.stop_btn.add_css_class("stop-button")
        self.stop_btn.connect("clicked", self.on_stop)
        self.stop_btn.set_visible(is_query_running())
        header.append(self.stop_btn)

        main_box.append(header)

        # Input row: text entry + send button
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Ask anything...")
        self.entry.add_css_class("query-entry")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", self.on_submit)
        input_row.append(self.entry)

        send_btn = Gtk.Button(label="")
        send_btn.add_css_class("send-button")
        send_btn.connect("clicked", self.on_submit)
        input_row.append(send_btn)

        main_box.append(input_row)

        # Separator
        sep1 = Gtk.Separator()
        sep1.add_css_class("separator")
        main_box.append(sep1)

        # Last response
        query, response, model = get_last_response()

        if query:
            q_label = Gtk.Label(label=f"Q: {query[:80]}")
            q_label.set_halign(Gtk.Align.START)
            q_label.set_wrap(True)
            q_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            q_label.add_css_class("stats-label")
            main_box.append(q_label)

        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(120)
        scroll.set_max_content_height(180)
        scroll.set_vexpand(True)

        self.response_label = Gtk.Label(label=response or "(No recent response)")
        self.response_label.set_halign(Gtk.Align.START)
        self.response_label.set_valign(Gtk.Align.START)
        self.response_label.set_wrap(True)
        self.response_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.response_label.set_selectable(True)
        self.response_label.add_css_class("response-text")
        scroll.set_child(self.response_label)
        main_box.append(scroll)

        if model:
            model_info = Gtk.Label(label=f"via {model}")
            model_info.set_halign(Gtk.Align.END)
            model_info.add_css_class("stats-label")
            main_box.append(model_info)

        # Separator
        sep2 = Gtk.Separator()
        sep2.add_css_class("separator")
        main_box.append(sep2)

        # Stats row
        stats = get_usage_stats()
        stats_text = (
            f"Today: {stats['total_queries']} queries · "
            f"avg {stats['avg_latency_ms']}ms"
        )
        self.stats_label = Gtk.Label(label=stats_text)
        self.stats_label.add_css_class("stats-label")
        self.stats_label.set_halign(Gtk.Align.START)
        main_box.append(self.stats_label)

        # Report status label (hidden by default)
        self.report_status = Gtk.Label(label="")
        self.report_status.add_css_class("report-status")
        self.report_status.set_halign(Gtk.Align.START)
        self.report_status.set_wrap(True)
        self.report_status.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.report_status.set_visible(False)
        main_box.append(self.report_status)

        # Bottom row: report button
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.report_btn = Gtk.Button(label="󰚑 Report bad answer")
        self.report_btn.add_css_class("report-button")
        self.report_btn.connect("clicked", self.on_report)
        bottom.append(self.report_btn)

        bottom.append(Gtk.Box(hexpand=True))

        history_btn = Gtk.Button(label="History")
        history_btn.add_css_class("stats-label")
        history_btn.connect("clicked", self.on_history)
        bottom.append(history_btn)

        main_box.append(bottom)

        self.win.set_child(main_box)

        # Periodic refresh
        GLib.timeout_add(1000, self.refresh)

        self.win.present()

    def refresh(self) -> bool:
        """Refresh dynamic elements."""
        running = is_query_running()
        self.stop_btn.set_visible(running)
        self.model_label.set_label(get_model_name())

        # Update response if changed
        _, response, _ = get_last_response()
        if response and response != self.response_label.get_label():
            self.response_label.set_label(response)

        return True  # keep timer running

    def on_submit(self, _widget):
        query = self.entry.get_text().strip()
        if not query:
            return
        self.entry.set_text("")
        self.entry.set_placeholder_text("Processing...")
        self.entry.set_sensitive(False)
        # Route through costa-ai which handles model selection, ML routing, logging
        subprocess.Popen(
            ["costa-ai", query],
            start_new_session=True,
        )
        # Re-enable after a short delay
        GLib.timeout_add(1500, self._reenable_entry)

    def _reenable_entry(self):
        self.entry.set_sensitive(True)
        self.entry.set_placeholder_text("Ask anything...")
        return False  # don't repeat

    def on_stop(self, _btn):
        stop_query()
        self.stop_btn.set_visible(False)

    def on_report(self, _btn):
        import threading

        # Find the report script
        report_script = None
        for path in [AI_ROUTER_DIR / "costa-ai-report",
                     INSTALLED_DIR / "costa-ai-report"]:
            if path.exists():
                report_script = str(path)
                break

        if not report_script:
            self._set_report_status("costa-ai-report not found", "error")
            return

        # Show progress in widget
        self.report_btn.set_sensitive(False)
        self._set_report_status("󰗊 Sending to Claude for correction...", "")

        def run_report():
            try:
                result = subprocess.run(
                    [report_script],
                    capture_output=True, text=True, timeout=45,
                )
                output = result.stdout.strip()
                if result.returncode == 0:
                    # Extract the correction from output
                    summary = output[:120] if output else "Correction applied"
                    GLib.idle_add(self._set_report_status,
                                  f"  {summary}", "done")
                    # Update the response label with the corrected answer
                    if output:
                        GLib.idle_add(self.response_label.set_label, output)
                else:
                    err = result.stderr.strip()[:80] or "Unknown error"
                    GLib.idle_add(self._set_report_status,
                                  f"  {err}", "error")
            except subprocess.TimeoutExpired:
                GLib.idle_add(self._set_report_status,
                              "  Timed out", "error")
            except Exception as e:
                GLib.idle_add(self._set_report_status,
                              f"  {str(e)[:80]}", "error")
            finally:
                GLib.idle_add(self.report_btn.set_sensitive, True)

        threading.Thread(target=run_report, daemon=True).start()

    def _set_report_status(self, text: str, css_class: str):
        self.report_status.set_label(text)
        self.report_status.set_visible(True)
        # Remove old state classes
        for cls in ("done", "error"):
            self.report_status.remove_css_class(cls)
        if css_class:
            self.report_status.add_css_class(css_class)

    def on_history(self, _btn):
        subprocess.Popen(
            ["ghostty", "--title=dropdown-costa-ai-history",
             "-e", "bash", "-c",
             "costa-ai --history 50 | less -R; read -n1 -p 'Press any key'"],
            start_new_session=True,
        )


if __name__ == "__main__":
    app = CostaAIWidget()
    app.run(None)
