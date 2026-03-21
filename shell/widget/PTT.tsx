import { createState } from "gnim"
import { execAsync } from "ags/process"
import GLib from "gi://GLib"

function readPttStatus(): string {
  try {
    const [ok, contents] = GLib.file_get_contents("/tmp/ptt-status")
    if (ok && contents) return new TextDecoder().decode(contents).trim()
  } catch {}
  return "ready"
}

const [getStatus, setStatus] = createState(readPttStatus())

GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
  setStatus(readPttStatus())
  return GLib.SOURCE_CONTINUE
})

export default function PTT() {
  return (
    <button
      class={getStatus.as((s) => `ptt ptt-${s}`)}
      tooltipText={getStatus.as((s) => {
        switch (s) {
          case "listening": return "Listening..."
          case "processing": return "Transcribing..."
          default: return "Push-to-talk ready (Super+Alt+V)"
        }
      })}
      onClicked={() =>
        execAsync("bash -c '~/.config/hypr/push-to-talk.sh'").catch(() => {})
      }
    >
      <label label={"\uF130"} />
    </button>
  )
}
