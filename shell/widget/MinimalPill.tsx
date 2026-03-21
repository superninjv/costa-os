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

const [getWorkspaces, setWorkspaces] = createState(hypr.get_workspaces())
const [getFocused, setFocused] = createState(hypr.get_focused_workspace())

hypr.connect("notify::workspaces", () => setWorkspaces(hypr.get_workspaces()))
hypr.connect("notify::focused-workspace", () => setFocused(hypr.get_focused_workspace()))

function PillWorkspaces() {
  const sorted = () =>
    getWorkspaces()
      .filter((ws) => ws.id > 0)
      .sort((a, b) => a.id - b.id)

  return (
    <box class="pill-workspaces" spacing={4}>
      {sorted().map((ws) => (
        <button
          class={getFocused.as(f => f?.id === ws.id ? "ws-dot active" : "ws-dot")}
          onClicked={() => hypr.dispatch("workspace", String(ws.id))}
        >
          <label label="" />
        </button>
      ))}
    </box>
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
      <box class="pill-panel" spacing={12}>
        <PillWorkspaces />
        <label label={getClock.as(v => v)} class="pill-clock" />
      </box>
    </window>
  )
}
