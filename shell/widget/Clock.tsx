import { Gtk } from "ags/gtk4"
import { createState } from "gnim"
import GLib from "gi://GLib"

const [getShowDate, setShowDate] = createState(false)

function getTime(): string {
  const now = GLib.DateTime.new_now_local()
  if (!now) return ""
  if (getShowDate()) {
    return now.format("%a %b %d") ?? ""
  }
  return now.format("%I:%M") ?? ""
}

const [getTimeStr, setTimeStr] = createState(getTime())

GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
  setTimeStr(getTime())
  return GLib.SOURCE_CONTINUE
})

export default function Clock() {
  return (
    <menubutton class="clock">
      <label label={getTimeStr.as(v => v)} />
      <popover>
        <Gtk.Calendar />
      </popover>
    </menubutton>
  )
}

// Toggle date/time on click handled by menubutton opening calendar
