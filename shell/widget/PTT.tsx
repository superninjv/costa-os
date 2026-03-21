import { createState } from "gnim"
import GLib from "gi://GLib"

function readPttStatus(): string {
  try {
    const [ok, contents] = GLib.file_get_contents("/tmp/ptt-status")
    if (ok && contents) {
      return new TextDecoder().decode(contents).trim()
    }
  } catch {
    // file doesn't exist
  }
  return "idle"
}

const [getPttStatus, setPttStatus] = createState(readPttStatus())

GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
  setPttStatus(readPttStatus())
  return GLib.SOURCE_CONTINUE
})

export default function PTT() {
  return (
    <box
      class={getPttStatus.as(s => `ptt ptt-${s}`)}
      tooltipText={getPttStatus.as(s => `PTT: ${s}`)}
    >
      <label label={getPttStatus.as(s => {
        switch (s) {
          case "listening": return "🎙"
          case "processing": return "⟳"
          default: return "🎤"
        }
      })} />
    </box>
  )
}
