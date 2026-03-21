import { Gtk } from "ags/gtk4"
import { createState } from "gnim"
import Hyprland from "gi://AstalHyprland"
import GLib from "gi://GLib"

const hypr = Hyprland.get_default()

export default function Workspaces() {
  const [getWorkspaces, setWorkspaces] = createState(hypr.get_workspaces())
  const [getFocused, setFocused] = createState(hypr.get_focused_workspace())

  hypr.connect("notify::workspaces", () => setWorkspaces(hypr.get_workspaces()))
  hypr.connect("notify::focused-workspace", () => setFocused(hypr.get_focused_workspace()))

  const sorted = () =>
    getWorkspaces()
      .filter((ws) => ws.id > 0)
      .sort((a, b) => a.id - b.id)

  return (
    <box class="workspaces">
      {sorted().map((ws) => (
        <button
          class={getFocused.as(f => f?.id === ws.id ? "ws-dot active" : "ws-dot")}
          onClicked={() =>
            hypr.dispatch("workspace", String(ws.id))
          }
        >
          <label label={String(ws.id)} />
        </button>
      ))}
    </box>
  )
}
