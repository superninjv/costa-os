import app from "ags/gtk4/app"
import style from "./style.scss"
import { Astal, Gtk, Gdk } from "ags/gtk4"
import Hyprland from "gi://AstalHyprland"

import Notch from "./widget/Notch"
import Bar from "./widget/Bar"
import MinimalPill from "./widget/MinimalPill"
import PortraitBar from "./widget/PortraitBar"
import ClaudeBar from "./widget/ClaudeBar"

const hypr = Hyprland.get_default()

function getMonitorType(connector: string): "primary" | "secondary" | "portrait" | "headless" {
  if (connector.startsWith("HEADLESS")) return "headless"
  if (connector === "HDMI-A-1") return "portrait"
  if (connector === "HDMI-A-2") return "secondary"
  if (connector.startsWith("DP-")) return "primary"
  return "primary"
}

app.start({
  css: style,
  main() {
    for (const gdkMon of app.get_monitors()) {
      const connector = gdkMon.get_connector() ?? "unknown"
      const type = getMonitorType(connector)
      print(`[costa-shell] ${connector} → ${type}`)

      switch (type) {
        case "primary":
          Notch(gdkMon)
          Bar(gdkMon)
          break
        case "secondary":
          MinimalPill(gdkMon)
          break
        case "portrait":
          PortraitBar(gdkMon)
          break
        case "headless":
          ClaudeBar(gdkMon)
          break
      }
    }
  },
})
