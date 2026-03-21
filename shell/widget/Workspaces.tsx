import { Gtk } from "ags/gtk4"
import Hyprland from "gi://AstalHyprland"

const hypr = Hyprland.get_default()

// Workspace icons matching waybar config
const WS_ICONS: Record<number, string> = {
  1: "\uF489", // terminal
  2: "\uF268", // browser
  3: "\uF121", // code
  4: "\uF013", // gear
  5: "\uF11B", // gamepad
  6: "\uF025", // headphones
  7: "\uF069", // claude/ai
}
const WS_DEFAULT = "\uF111" // solid circle

function clearChildren(box: Gtk.Box) {
  let child = box.get_first_child()
  while (child) {
    const next = child.get_next_sibling()
    box.remove(child)
    child = next
  }
}

export default function Workspaces() {
  return (
    <box
      class="workspaces"
      spacing={2}
      $={(self: Gtk.Box) => {
        const update = () => {
          clearChildren(self)
          const wss = hypr.get_workspaces().filter((ws) => ws.id > 0).sort((a, b) => a.id - b.id)
          const focused = hypr.get_focused_workspace()
          for (const ws of wss) {
            const icon = WS_ICONS[ws.id] ?? WS_DEFAULT
            const btn = new Gtk.Button({
              cssClasses: ws.id === focused?.id ? ["ws-btn", "active"] : ["ws-btn"],
            })
            btn.connect("clicked", () => hypr.dispatch("workspace", String(ws.id)))
            btn.set_child(new Gtk.Label({ label: icon }))
            self.append(btn)
          }
        }
        hypr.connect("notify::workspaces", update)
        hypr.connect("notify::focused-workspace", update)
        update()
      }}
    />
  )
}
