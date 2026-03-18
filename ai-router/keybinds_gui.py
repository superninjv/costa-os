#!/usr/bin/env python3
"""Costa OS Keybind & Mouse Configurator — GTK4/libadwaita GUI.

Wraps the keybinds.py backend with a visual interface for managing
Hyprland keyboard and mouse bindings.
"""

import os
import sys
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, Gdk, GLib, Gio, Pango

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import keybinds

# ─── Costa palette (CSS) ───

COSTA_CSS = """
@define-color accent_bg_color #5b94a8;
@define-color accent_fg_color #d4cfc4;
@define-color accent_color #5b94a8;
@define-color window_bg_color #1b1d2b;
@define-color window_fg_color #d4cfc4;
@define-color headerbar_bg_color #161821;
@define-color headerbar_fg_color #d4cfc4;
@define-color card_bg_color #252836;
@define-color card_fg_color #d4cfc4;
@define-color view_bg_color #1b1d2b;
@define-color view_fg_color #d4cfc4;
@define-color sidebar_bg_color #161821;
@define-color sidebar_fg_color #d4cfc4;
@define-color popover_bg_color #2f3345;
@define-color popover_fg_color #d4cfc4;
@define-color dialog_bg_color #252836;
@define-color dialog_fg_color #d4cfc4;

.shortcut-label {
    font-family: "JetBrains Mono Nerd Font", monospace;
    font-size: 0.85em;
    padding: 2px 8px;
    border-radius: 6px;
    background: alpha(#5b94a8, 0.15);
    color: #7eb5b0;
}

.category-title {
    color: #c9a96e;
    font-weight: bold;
    font-size: 0.9em;
}

.mouse-device-title {
    color: #5b94a8;
    font-weight: bold;
}

.detecting-button {
    color: #c07a56;
    font-style: italic;
}

.conflict-warning {
    color: #b87272;
    font-weight: bold;
}

.info-banner {
    background: alpha(#5b94a8, 0.1);
    border-radius: 8px;
    padding: 12px;
    margin: 6px 0;
}
"""


class KeybindRow(Adw.ActionRow):
    """A row displaying a single keybind with edit/delete buttons."""

    def __init__(self, bind_data: dict, variables: dict, on_edit=None, on_delete=None):
        super().__init__()
        self.bind_data = bind_data
        self.variables = variables
        self._on_edit = on_edit
        self._on_delete = on_delete

        # Resolve variables for display
        mods = keybinds.substitute_variables(bind_data["mods"], variables)
        key = bind_data["key"]
        combo = f"{mods} + {key}" if mods else key

        # Title = description or action
        desc = bind_data["description"]
        action = f"{bind_data['dispatcher']} {bind_data['args']}".strip()
        action_display = keybinds.substitute_variables(action, variables)

        self.set_title(desc if desc else action_display)
        if desc:
            self.set_subtitle(action_display)

        # Shortcut label as prefix
        shortcut_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4,
                               valign=Gtk.Align.CENTER)
        shortcut_lbl = Gtk.Label(label=combo)
        shortcut_lbl.add_css_class("shortcut-label")
        shortcut_box.append(shortcut_lbl)

        # Bind type badge if not plain "bind"
        if bind_data["type"] != "bind":
            type_lbl = Gtk.Label(label=bind_data["type"])
            type_lbl.set_opacity(0.6)
            type_lbl.set_margin_start(4)
            shortcut_box.append(type_lbl)

        self.add_prefix(shortcut_box)

        # Edit button
        edit_btn = Gtk.Button(icon_name="document-edit-symbolic",
                              valign=Gtk.Align.CENTER, has_frame=False,
                              tooltip_text="Edit keybind")
        edit_btn.connect("clicked", self._edit_clicked)
        self.add_suffix(edit_btn)

        # Delete button
        del_btn = Gtk.Button(icon_name="user-trash-symbolic",
                             valign=Gtk.Align.CENTER, has_frame=False,
                             tooltip_text="Remove keybind")
        del_btn.connect("clicked", self._delete_clicked)
        self.add_suffix(del_btn)

    def _edit_clicked(self, _btn):
        if self._on_edit:
            self._on_edit(self.bind_data)

    def _delete_clicked(self, _btn):
        if self._on_delete:
            self._on_delete(self.bind_data)


class MouseButtonRow(Adw.ActionRow):
    """A row displaying a single mouse button with its binding status."""

    def __init__(self, code: int, device_name: str, hypr_binds: list,
                 on_configure=None):
        super().__init__()
        self.button_code = code
        self.device_name = device_name
        self._on_configure = on_configure

        name = keybinds.get_button_name(code)
        hypr_code = f"mouse:{code}"

        self.set_title(name)
        self.set_subtitle(hypr_code)

        # Check if this button has a Hyprland binding
        bound_to = None
        for hb in hypr_binds:
            if hb.get("key", "") == hypr_code:
                bound_to = f"{hb.get('dispatcher', '')} {hb.get('arg', '')}".strip()
                break

        if bound_to:
            status = Gtk.Label(label=f"→ {bound_to}", valign=Gtk.Align.CENTER)
            status.set_opacity(0.8)
            status.set_ellipsize(Pango.EllipsizeMode.END)
            status.set_max_width_chars(30)
            self.add_suffix(status)

        # Configure button
        if code not in (272, 273, 274):  # Skip left/right/middle
            cfg_btn = Gtk.Button(label="Configure", valign=Gtk.Align.CENTER,
                                 has_frame=True)
            cfg_btn.connect("clicked", self._configure_clicked)
            self.add_suffix(cfg_btn)

    def _configure_clicked(self, _btn):
        if self._on_configure:
            self._on_configure(self.button_code, self.device_name)


class EditKeybindDialog(Adw.Dialog):
    """Dialog for adding or editing a keybind."""

    def __init__(self, bind_data: dict = None, variables: dict = None,
                 on_save=None):
        super().__init__()
        self.set_title("Edit Keybind" if bind_data else "Add Keybind")
        self.set_content_width(500)
        self.set_content_height(420)
        self._bind_data = bind_data
        self._variables = variables or {}
        self._on_save = on_save
        self._recording = False

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        # Save button in header
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save_clicked)
        header.pack_end(save_btn)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                          margin_top=12, margin_bottom=12,
                          margin_start=12, margin_end=12)

        # ─── Shortcut capture ───
        shortcut_group = Adw.PreferencesGroup(title="Key Combination")

        # Record button
        self._record_row = Adw.ActionRow(title="Press keys to record",
                                         subtitle="Click 'Record', then press your shortcut")
        self._record_btn = Gtk.Button(label="Record", valign=Gtk.Align.CENTER)
        self._record_btn.connect("clicked", self._toggle_record)
        self._record_row.add_suffix(self._record_btn)
        shortcut_group.add(self._record_row)

        # Manual entry fallback
        self._manual_row = Adw.EntryRow(title="Or type manually (e.g. SUPER+SHIFT, K)")
        if bind_data:
            combo = f"{bind_data['mods']}, {bind_data['key']}" if bind_data["mods"] else bind_data["key"]
            self._manual_row.set_text(combo)
        shortcut_group.add(self._manual_row)

        content.append(shortcut_group)

        # ─── Action ───
        action_group = Adw.PreferencesGroup(title="Action")

        # Dispatcher dropdown
        dispatchers = ["exec", "killactive", "togglefloating", "fullscreen",
                       "workspace", "movetoworkspace", "movefocus", "movewindow",
                       "resizeactive", "pseudo", "togglesplit", "exit",
                       "focusmonitor", "pin", "centerwindow"]
        self._dispatcher_model = Gtk.StringList.new(dispatchers)
        self._dispatcher_row = Adw.ComboRow(title="Dispatcher",
                                            model=self._dispatcher_model)
        if bind_data:
            try:
                idx = dispatchers.index(bind_data["dispatcher"])
                self._dispatcher_row.set_selected(idx)
            except ValueError:
                pass
        action_group.add(self._dispatcher_row)

        # Args entry
        self._args_row = Adw.EntryRow(title="Arguments")
        if bind_data:
            self._args_row.set_text(bind_data["args"])
        action_group.add(self._args_row)

        # Bind type
        bind_types = ["bind", "binde", "bindm", "bindl", "bindr", "bindn"]
        self._type_model = Gtk.StringList.new(bind_types)
        self._type_row = Adw.ComboRow(title="Bind type", model=self._type_model)
        if bind_data:
            try:
                idx = bind_types.index(bind_data["type"])
                self._type_row.set_selected(idx)
            except ValueError:
                pass
        action_group.add(self._type_row)

        content.append(action_group)

        # ─── Comment ───
        comment_group = Adw.PreferencesGroup(title="Description")
        self._comment_row = Adw.EntryRow(title="Comment (shown above bind in config)")
        if bind_data and bind_data.get("description"):
            self._comment_row.set_text(bind_data["description"])
        comment_group.add(self._comment_row)
        content.append(comment_group)

        # ─── Conflict warning ───
        self._conflict_label = Gtk.Label(label="", wrap=True, xalign=0)
        self._conflict_label.add_css_class("conflict-warning")
        self._conflict_label.set_visible(False)
        content.append(self._conflict_label)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(content)
        toolbar.set_content(scroll)
        self.set_child(toolbar)

        # Key event controller for recording
        self._key_ctrl = Gtk.EventControllerKey()
        self._key_ctrl.connect("key-pressed", self._on_key_pressed)

    def _toggle_record(self, _btn):
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._recording = True
        self._record_btn.set_label("Stop")
        self._record_btn.add_css_class("destructive-action")
        self._record_row.set_title("Press your key combination now...")
        self._record_row.add_css_class("detecting-button")
        # Add key controller to the dialog's content widget
        child = self.get_child()
        if child:
            child.add_controller(self._key_ctrl)

    def _stop_recording(self):
        self._recording = False
        self._record_btn.set_label("Record")
        self._record_btn.remove_css_class("destructive-action")
        self._record_row.remove_css_class("detecting-button")
        child = self.get_child()
        if child:
            child.remove_controller(self._key_ctrl)

    def _on_key_pressed(self, _ctrl, keyval, keycode, state):
        if not self._recording:
            return False

        # Build modifier string
        mods = []
        if state & Gdk.ModifierType.SUPER_MASK:
            mods.append("SUPER")
        if state & Gdk.ModifierType.ALT_MASK:
            mods.append("ALT")
        if state & Gdk.ModifierType.CONTROL_MASK:
            mods.append("CTRL")
        if state & Gdk.ModifierType.SHIFT_MASK:
            mods.append("SHIFT")

        key_name = Gdk.keyval_name(keyval)
        if not key_name or key_name in ("Super_L", "Super_R", "Alt_L", "Alt_R",
                                         "Control_L", "Control_R", "Shift_L", "Shift_R"):
            return True  # Just a modifier, keep recording

        mod_str = " ".join(mods)
        combo = f"{mod_str}, {key_name}" if mod_str else key_name
        self._manual_row.set_text(combo)
        self._record_row.set_title(f"Recorded: {mod_str} + {key_name}" if mod_str else f"Recorded: {key_name}")

        self._stop_recording()
        self._check_conflicts(mod_str, key_name)
        return True

    def _check_conflicts(self, mods: str, key: str):
        """Check for conflicting binds."""
        active = keybinds.get_active_binds()
        mods_upper = mods.upper().replace(" ", "")
        # Resolve $mainMod for comparison
        mods_resolved = keybinds.substitute_variables(mods_upper, self._variables).upper()
        for ab in active:
            ab_mods = ab.get("modmask", 0)
            ab_key = ab.get("key", "")
            # Simple string comparison (not perfect but good enough for common cases)
            if ab_key.upper() == key.upper():
                self._conflict_label.set_text(
                    f"Warning: '{key}' is already bound to "
                    f"{ab.get('dispatcher', '?')} {ab.get('arg', '')}")
                self._conflict_label.set_visible(True)
                return
        self._conflict_label.set_visible(False)

    def _on_save_clicked(self, _btn):
        combo_text = self._manual_row.get_text().strip()
        if not combo_text:
            return

        # Parse "MODS, KEY" or just "KEY"
        if "," in combo_text:
            parts = combo_text.split(",", 1)
            mods = parts[0].strip()
            key = parts[1].strip()
        else:
            mods = ""
            key = combo_text

        # Use $mainMod if SUPER is specified and config uses it
        if "mainMod" in self._variables and self._variables["mainMod"] == "SUPER":
            mods = mods.replace("SUPER", "$mainMod")

        idx = self._dispatcher_row.get_selected()
        dispatcher = self._dispatcher_model.get_string(idx)
        args = self._args_row.get_text().strip()

        type_idx = self._type_row.get_selected()
        bind_type = self._type_model.get_string(type_idx)

        comment = self._comment_row.get_text().strip()

        if self._on_save:
            self._on_save(self._bind_data, {
                "mods": mods,
                "key": key,
                "dispatcher": dispatcher,
                "args": args,
                "type": bind_type,
                "comment": comment,
            })

        self.close()


class ConfigureMouseDialog(Adw.Dialog):
    """Dialog for configuring a mouse button binding."""

    def __init__(self, button_code: int, device_name: str, on_save=None):
        super().__init__()
        self.set_title(f"Configure {keybinds.get_button_name(button_code)}")
        self.set_content_width(450)
        self.set_content_height(300)
        self._button_code = button_code
        self._on_save = on_save

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._save_clicked)
        header.pack_end(save_btn)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                          margin_top=12, margin_bottom=12,
                          margin_start=12, margin_end=12)

        info = Adw.PreferencesGroup(title="Mouse Button")
        info_row = Adw.ActionRow(
            title=keybinds.get_button_name(button_code),
            subtitle=f"mouse:{button_code} on {device_name}")
        info.add(info_row)
        content.append(info)

        action_group = Adw.PreferencesGroup(title="Bind to Action")

        dispatchers = ["exec", "workspace", "movetoworkspace", "togglefloating",
                       "fullscreen", "killactive", "pin"]
        self._dispatcher_model = Gtk.StringList.new(dispatchers)
        self._dispatcher_row = Adw.ComboRow(title="Dispatcher",
                                            model=self._dispatcher_model)
        action_group.add(self._dispatcher_row)

        self._args_row = Adw.EntryRow(title="Arguments (e.g. command to exec)")
        action_group.add(self._args_row)

        # Modifier for the bind
        self._mods_row = Adw.EntryRow(title="Modifiers (leave empty for none)")
        action_group.add(self._mods_row)

        content.append(action_group)

        toolbar.set_content(content)
        self.set_child(toolbar)

    def _save_clicked(self, _btn):
        idx = self._dispatcher_row.get_selected()
        dispatcher = self._dispatcher_model.get_string(idx)
        args = self._args_row.get_text().strip()
        mods = self._mods_row.get_text().strip()

        if self._on_save:
            self._on_save(self._button_code, mods, dispatcher, args)

        self.close()


class KeybindsWindow(Adw.ApplicationWindow):
    """Main application window with Keyboard/Mouse tabs."""

    def __init__(self, app):
        super().__init__(application=app, title="Costa Keybinds", default_width=850,
                         default_height=650)
        self._variables = {}
        self._conf_text = ""

        # Load CSS
        css = Gtk.CssProvider()
        css.load_from_string(COSTA_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # Main layout
        toolbar_view = Adw.ToolbarView()

        # Header bar with view switcher
        header = Adw.HeaderBar()
        self._view_stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self._view_stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        # Add button in header
        add_btn = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Add Keybind")
        add_btn.connect("clicked", self._on_add_keybind)
        header.pack_start(add_btn)

        # Refresh button
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh")
        refresh_btn.connect("clicked", lambda _: self._refresh_all())
        header.pack_end(refresh_btn)

        toolbar_view.add_top_bar(header)

        # ─── Keyboard tab ───
        kb_page = self._build_keyboard_tab()
        self._view_stack.add_titled_with_icon(kb_page, "keyboard", "Keyboard",
                                              "input-keyboard-symbolic")

        # ─── Mouse tab ───
        mouse_page = self._build_mouse_tab()
        self._view_stack.add_titled_with_icon(mouse_page, "mouse", "Mouse",
                                              "input-mouse-symbolic")

        toolbar_view.set_content(self._view_stack)
        self.set_content(toolbar_view)

        # Load data
        self._refresh_all()

    def _build_keyboard_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Search bar
        self._search_entry = Gtk.SearchEntry(placeholder_text="Filter keybinds...",
                                             margin_start=12, margin_end=12,
                                             margin_top=8, margin_bottom=4)
        self._search_entry.connect("search-changed", self._on_search_changed)
        box.append(self._search_entry)

        # Scrollable content
        scroll = Gtk.ScrolledWindow(vexpand=True)
        self._kb_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                                   margin_start=12, margin_end=12,
                                   margin_top=4, margin_bottom=12)
        scroll.set_child(self._kb_content)
        box.append(scroll)

        return box

    def _build_mouse_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        self._mouse_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                                      margin_start=12, margin_end=12,
                                      margin_top=8, margin_bottom=12)
        scroll.set_child(self._mouse_content)
        box.append(scroll)

        return box

    def _refresh_all(self):
        self._load_keyboard_tab()
        self._load_mouse_tab()

    def _load_keyboard_tab(self, filter_text: str = ""):
        # Clear existing
        while child := self._kb_content.get_first_child():
            self._kb_content.remove(child)

        # Read config and resolve variables
        try:
            self._conf_text = keybinds.HYPR_CONF.read_text()
            self._variables = keybinds.resolve_variables(self._conf_text)
        except FileNotFoundError:
            lbl = Gtk.Label(label="hyprland.conf not found")
            self._kb_content.append(lbl)
            return

        all_binds = keybinds.parse_keybinds()

        # Filter
        if filter_text:
            ft = filter_text.lower()
            all_binds = [b for b in all_binds
                         if ft in b["key"].lower()
                         or ft in b["mods"].lower()
                         or ft in b["dispatcher"].lower()
                         or ft in b["args"].lower()
                         or ft in b["description"].lower()
                         or ft in keybinds.substitute_variables(
                             b["mods"], self._variables).lower()]

        # Categorize
        categories = keybinds.categorize_keybinds(all_binds)

        # Preferred category order
        order = ["Applications", "Launchers & Clipboard", "Window Management",
                 "Workspaces", "Monitors", "Mouse", "Media", "Screenshots",
                 "Costa AI", "Session", "Other"]

        for cat_name in order:
            cat_binds = categories.get(cat_name)
            if not cat_binds:
                continue

            # Escape ampersands for Pango markup in group titles
            safe_name = cat_name.replace("&", "&amp;")
            group = Adw.PreferencesGroup(title=safe_name)
            group.add_css_class("category-title")

            for b in cat_binds:
                row = KeybindRow(b, self._variables,
                                 on_edit=self._on_edit_keybind,
                                 on_delete=self._on_delete_keybind)
                group.add(row)

            self._kb_content.append(group)

        # Any remaining categories not in order
        for cat_name, cat_binds in categories.items():
            if cat_name in order:
                continue
            safe_name = cat_name.replace("&", "&amp;")
            group = Adw.PreferencesGroup(title=safe_name)
            for b in cat_binds:
                row = KeybindRow(b, self._variables,
                                 on_edit=self._on_edit_keybind,
                                 on_delete=self._on_delete_keybind)
                group.add(row)
            self._kb_content.append(group)

    def _load_mouse_tab(self):
        # Clear existing
        while child := self._mouse_content.get_first_child():
            self._mouse_content.remove(child)

        # Get active Hyprland binds for checking what's bound
        active_binds = keybinds.get_active_binds()

        # Discover mice
        mice = keybinds.discover_mice()

        if not mice:
            no_mice = Adw.StatusPage(
                title="No Mice Detected",
                description="No mouse devices found via evdev.\nMake sure you're in the 'input' group.",
                icon_name="input-mouse-symbolic")
            self._mouse_content.append(no_mice)
            return

        # Ratbag availability banner
        if not keybinds.has_ratbagctl():
            banner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            banner_box.add_css_class("info-banner")
            icon = Gtk.Image(icon_name="dialog-information-symbolic")
            banner_box.append(icon)
            lbl = Gtk.Label(
                label="Install libratbag + ratbagctl for hardware button remapping (DPI shift, etc). "
                      "Keybinding via Hyprland works without it.",
                wrap=True, xalign=0)
            banner_box.append(lbl)
            self._mouse_content.append(banner_box)

        # "Press to Detect" section
        detect_group = Adw.PreferencesGroup(title="Button Detection")
        self._detect_row = Adw.ActionRow(
            title="Press to Detect",
            subtitle="Click the button below, then press a mouse button to identify it")
        self._detect_btn = Gtk.Button(label="Start Detection", valign=Gtk.Align.CENTER)
        self._detect_btn.connect("clicked", self._on_detect_mouse)
        self._detect_row.add_suffix(self._detect_btn)
        detect_group.add(self._detect_row)
        self._mouse_content.append(detect_group)

        # Per-device groups
        for mouse in mice:
            group = Adw.PreferencesGroup(
                title=mouse["name"],
                description=f"{mouse['path']} — {len(mouse['buttons'])} buttons")
            group.add_css_class("mouse-device-title")

            for code in mouse["buttons"]:
                row = MouseButtonRow(code, mouse["name"], active_binds,
                                     on_configure=self._on_configure_mouse_button)
                group.add(row)

            self._mouse_content.append(group)

    # ─── Callbacks ───

    def _on_search_changed(self, entry):
        self._load_keyboard_tab(filter_text=entry.get_text())

    def _on_add_keybind(self, _btn):
        dialog = EditKeybindDialog(variables=self._variables, on_save=self._save_keybind)
        dialog.present(self)

    def _on_edit_keybind(self, bind_data):
        dialog = EditKeybindDialog(bind_data=bind_data, variables=self._variables,
                                   on_save=self._save_keybind)
        dialog.present(self)

    def _on_delete_keybind(self, bind_data):
        # Confirmation dialog
        dialog = Adw.AlertDialog(
            heading="Remove Keybind?",
            body=f"Remove {bind_data['mods']}+{bind_data['key']} → "
                 f"{bind_data['dispatcher']} {bind_data['args']}?")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Remove")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_delete_confirmed, bind_data)
        dialog.present(self)

    def _on_delete_confirmed(self, dialog, response, bind_data):
        if response != "delete":
            return
        result = keybinds.remove_keybind(bind_data["mods"], bind_data["key"])
        if result["success"]:
            self._load_keyboard_tab(self._search_entry.get_text())
        else:
            self._show_error("Failed to remove keybind", result.get("error", "Unknown error"))

    def _save_keybind(self, old_data, new_data):
        """Save a new or modified keybind."""
        if old_data:
            # Remove old first, then add new
            keybinds.remove_keybind(old_data["mods"], old_data["key"])

        result = keybinds.add_keybind(
            new_data["mods"], new_data["key"],
            new_data["dispatcher"], new_data["args"],
            bind_type=new_data["type"], comment=new_data["comment"])

        if result["success"]:
            self._load_keyboard_tab(self._search_entry.get_text())
        else:
            self._show_error("Failed to save keybind", result.get("error", "Unknown error"))

    def _on_detect_mouse(self, _btn):
        self._detect_btn.set_sensitive(False)
        self._detect_btn.set_label("Press a button...")
        self._detect_row.set_subtitle("Waiting for mouse button press (10 seconds)...")
        self._detect_row.add_css_class("detecting-button")

        def _detect():
            result = keybinds.detect_mouse_button_evdev(timeout_secs=10)
            GLib.idle_add(self._on_detect_result, result)

        thread = threading.Thread(target=_detect, daemon=True)
        thread.start()

    def _on_detect_result(self, result):
        self._detect_btn.set_sensitive(True)
        self._detect_btn.set_label("Start Detection")
        self._detect_row.remove_css_class("detecting-button")

        if result:
            self._detect_row.set_title(f"Detected: {result['button_name']}")
            self._detect_row.set_subtitle(
                f"{result['hypr_code']} on {result['device_name']}")
        else:
            self._detect_row.set_title("Press to Detect")
            self._detect_row.set_subtitle("No button press detected. Try again.")
        return False  # Remove from idle

    def _on_configure_mouse_button(self, button_code, device_name):
        dialog = ConfigureMouseDialog(button_code, device_name,
                                      on_save=self._save_mouse_bind)
        dialog.present(self)

    def _save_mouse_bind(self, button_code, mods, dispatcher, args):
        """Add a Hyprland bind for a mouse button."""
        key = f"mouse:{button_code}"
        result = keybinds.add_keybind(mods, key, dispatcher, args,
                                      comment=f"Mouse {keybinds.get_button_name(button_code)}")
        if result["success"]:
            self._load_mouse_tab()
        else:
            self._show_error("Failed to bind mouse button",
                             result.get("error", "Unknown error"))

    def _show_error(self, title, message):
        dialog = Adw.AlertDialog(heading=title, body=message)
        dialog.add_response("ok", "OK")
        dialog.present(self)


class KeybindsApp(Adw.Application):

    def __init__(self):
        super().__init__(application_id="com.costa.keybinds",
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        win = self.get_active_window()
        if not win:
            win = KeybindsWindow(self)
        win.present()


def main():
    app = KeybindsApp()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
