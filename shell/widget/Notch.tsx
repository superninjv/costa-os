import app from "ags/gtk4/app"
import { Astal, Gtk, Gdk } from "ags/gtk4"
import Gtk4LayerShell from "gi://Gtk4LayerShell"
import { revealBar, hideBar } from "../lib/state"

export default function Notch(gdkmonitor: Gdk.Monitor) {
  const win = new Gtk.Window()
  win.set_default_size(800, 4)

  Gtk4LayerShell.init_for_window(win)
  Gtk4LayerShell.set_layer(win, Gtk4LayerShell.Layer.OVERLAY)
  Gtk4LayerShell.set_namespace(win, "costa-notch")
  Gtk4LayerShell.set_monitor(win, gdkmonitor)

  // Anchor TOP + LEFT + RIGHT but set exclusive zone to -1
  Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.TOP, true)
  Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.LEFT, false)
  Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.RIGHT, false)

  // No exclusive zone — overlay only, don't push windows
  Gtk4LayerShell.set_exclusive_zone(win, -1)

  const box = new Gtk.Box({ halign: Gtk.Align.CENTER })
  const trigger = new Gtk.Box({ cssClasses: ["notch-trigger"] })

  const motion = new Gtk.EventControllerMotion()
  motion.connect("enter", () => revealBar())
  motion.connect("leave", () => hideBar(1200))
  trigger.add_controller(motion)

  box.append(trigger)
  win.set_child(box)
  win.add_css_class("Notch")

  const display = Gdk.Display.get_default()
  if (display) {
    const provider = new Gtk.CssProvider()
    provider.load_from_string(`
      .Notch { background: transparent; }
      .notch-trigger {
        min-width: 800px;
        min-height: 4px;
        background-color: rgba(126, 181, 176, 0.15);
        border-radius: 0px 0px 4px 4px;
      }
      .notch-trigger:hover {
        background-color: rgba(126, 181, 176, 0.35);
        min-height: 5px;
      }
    `)
    Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
  }

  win.present()
  return win
}
