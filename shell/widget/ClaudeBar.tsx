import app from "ags/gtk4/app"
import { Astal, Gtk, Gdk } from "ags/gtk4"
import { createState } from "gnim"
import GLib from "gi://GLib"

const { TOP } = Astal.WindowAnchor

const [getClock, setClock] = createState("")
function updateClock() {
  const now = GLib.DateTime.new_now_local()
  setClock(now?.format("%H:%M") ?? "")
}
updateClock()
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
  updateClock()
  return GLib.SOURCE_CONTINUE
})

export default function ClaudeBar(gdkmonitor: Gdk.Monitor) {
  return (
    <window
      visible={true}
      name="costa-claude-screen"
      class="ClaudeBar"
      gdkmonitor={gdkmonitor}
      layer={Astal.Layer.TOP}
      anchor={TOP}
      exclusivity={Astal.Exclusivity.IGNORE}
      namespace="costa-claude-screen"
      application={app}
    >
      <box class="claude-bar-panel" spacing={8} valign={Gtk.Align.CENTER}>
        <label label={"\uF069"} class="claude-icon" />
        <label label="Claude Screen" class="claude-label" />
        <label label={getClock.as((v) => v)} class="claude-clock" />
      </box>
    </window>
  )
}
