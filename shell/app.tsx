import app from "ags/gtk4/app"
import style from "./style.scss"
import { Astal, Gtk, Gdk } from "ags/gtk4"
import GLib from "gi://GLib"
import Hyprland from "gi://AstalHyprland"

import Notch from "./widget/Notch"
import Bar from "./widget/Bar"
import MinimalPill from "./widget/MinimalPill"
import PortraitBar from "./widget/PortraitBar"
import ClaudeBar from "./widget/ClaudeBar"

const hypr = Hyprland.get_default()

// Track active monitors to prevent duplicates and enable cleanup
const activeMonitors = new Map<string, Gtk.Window[]>()

function getMonitorType(connector: string): "primary" | "secondary" | "portrait" | "headless" {
  if (connector.startsWith("HEADLESS")) return "headless"
  // Read monitor config if it exists — allows user/first-boot to assign roles
  try {
    const [ok, bytes] = GLib.file_get_contents(
      GLib.get_home_dir() + "/.config/costa/monitor-roles.json"
    )
    if (ok && bytes) {
      const roles = JSON.parse(new TextDecoder().decode(bytes))
      if (roles[connector]) return roles[connector]
    }
  } catch {}
  // Fallback: first non-headless monitor is primary, rest are secondary
  // eDP = laptop built-in = primary
  if (connector.startsWith("eDP")) return "primary"
  if (connector.startsWith("DP-")) return "primary"
  if (connector.startsWith("HDMI-")) return "secondary"
  return "primary"
}

function setupMonitor(gdkMon: Gdk.Monitor) {
  const connector = gdkMon.get_connector() ?? "unknown"

  if (activeMonitors.has(connector)) {
    print(`[costa-shell] ${connector} already active, skipping`)
    return
  }

  const type = getMonitorType(connector)
  print(`[costa-shell] ${connector} → ${type}`)
  const windows: Gtk.Window[] = []

  switch (type) {
    case "primary":
      windows.push(Notch(gdkMon))
      windows.push(Bar(gdkMon))
      break
    case "secondary":
      windows.push(MinimalPill(gdkMon))
      break
    case "portrait":
      windows.push(PortraitBar(gdkMon))
      break
    case "headless":
      windows.push(ClaudeBar(gdkMon))
      break
  }

  activeMonitors.set(connector, windows)
}

function teardownMonitor(connector: string) {
  const windows = activeMonitors.get(connector)
  if (!windows) return

  print(`[costa-shell] ${connector} removed, destroying ${windows.length} windows`)
  for (const win of windows) {
    win.close()
  }
  activeMonitors.delete(connector)
}

function reconcileMonitors(monitorList: import("gi://Gio").ListModel) {
  const currentConnectors = new Set<string>()
  const n = monitorList.get_n_items()
  for (let i = 0; i < n; i++) {
    const mon = monitorList.get_item(i) as Gdk.Monitor
    const c = mon?.get_connector()
    if (c) currentConnectors.add(c)
  }

  // Tear down monitors that disappeared
  for (const connector of activeMonitors.keys()) {
    if (!currentConnectors.has(connector)) {
      teardownMonitor(connector)
    }
  }

  // Set up monitors that are new (setupMonitor deduplicates)
  for (let i = 0; i < n; i++) {
    const mon = monitorList.get_item(i) as Gdk.Monitor
    if (mon) setupMonitor(mon)
  }
}

app.start({
  css: style,
  main() {
    // Set up monitors already present
    for (const gdkMon of app.get_monitors()) {
      setupMonitor(gdkMon)
    }

    // Reconcile on any monitor change (hotplug, EDID, reboot timing)
    const display = Gdk.Display.get_default()
    if (display) {
      const monitorList = display.get_monitors() as import("gi://Gio").ListModel
      monitorList.connect("items-changed", () => reconcileMonitors(monitorList))
    }
  },
})
