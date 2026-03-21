import app from "ags/gtk4/app"
import { Astal, Gtk, Gdk } from "ags/gtk4"
import { createState } from "gnim"
import GLib from "gi://GLib"
import Hyprland from "gi://AstalHyprland"

const hypr = Hyprland.get_default()
const { TOP } = Astal.WindowAnchor

const [getClock, setClock] = createState("")
function updateClock() {
  const now = GLib.DateTime.new_now_local()
  setClock(now?.format("%I:%M") ?? "")
}
updateClock()
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
  updateClock()
  return GLib.SOURCE_CONTINUE
})

function clearChildren(box: Gtk.Box) {
  let child = box.get_first_child()
  while (child) {
    const next = child.get_next_sibling()
    box.remove(child)
    child = next
  }
}

function DotWorkspaces() {
  return (
    <box
      class="pill-workspaces"
      spacing={4}
      $={(self: Gtk.Box) => {
        const update = () => {
          clearChildren(self)
          const wss = hypr.get_workspaces().filter((ws) => ws.id > 0).sort((a, b) => a.id - b.id)
          const focused = hypr.get_focused_workspace()
          for (const ws of wss) {
            const btn = new Gtk.Button({
              cssClasses: ws.id === focused?.id ? ["ws-dot", "active"] : ["ws-dot"],
              widthRequest: 12,
              heightRequest: 12,
              valign: Gtk.Align.CENTER,
            })
            btn.connect("clicked", () => hypr.dispatch("workspace", String(ws.id)))
            btn.set_child(new Gtk.Label({ label: "" }))
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

export default function MinimalPill(gdkmonitor: Gdk.Monitor) {
  return (
    <window
      visible={true}
      name="costa-minimal"
      class="MinimalPill"
      gdkmonitor={gdkmonitor}
      layer={Astal.Layer.TOP}
      anchor={TOP}
      exclusivity={Astal.Exclusivity.IGNORE}
      namespace="costa-minimal"
      application={app}
    >
      <box class="pill-panel" spacing={16}>
        <DotWorkspaces />
        <label label={getClock.as((v) => v)} class="pill-clock" />
      </box>
    </window>
  )
}
