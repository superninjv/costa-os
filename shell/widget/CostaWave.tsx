import { createState } from "gnim"
import GLib from "gi://GLib"

const [getWaveClass, setWaveClass] = createState(0)

GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1300, () => {
  setWaveClass((getWaveClass() + 1) % 3)
  return GLib.SOURCE_CONTINUE
})

interface PttState {
  text: string
  cssClass: string
}

function readPttStatus(): PttState {
  try {
    const [ok, contents] = GLib.file_get_contents("/tmp/ptt-voice-status")
    if (ok && contents) {
      const status = new TextDecoder().decode(contents).trim()
      switch (status) {
        case "running":
          return { text: "\u27F3", cssClass: "wave-running" }
        case "done":
          return { text: "\u2713", cssClass: "wave-done" }
        case "interactive":
          return { text: "\u25C9", cssClass: "wave-interactive" }
        default:
          return { text: "\u3030", cssClass: "" }
      }
    }
  } catch {
    // file doesn't exist yet
  }
  return { text: "\u3030", cssClass: "" }
}

const [getPttState, setPttState] = createState(readPttStatus())

GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
  setPttState(readPttStatus())
  return GLib.SOURCE_CONTINUE
})

export default function CostaWave() {
  return (
    <box class="costa-wave">
      <label
        label={getPttState.as(ps => ps.text)}
        class={getPttState.as(ps => {
          if (ps.cssClass) return `wave ${ps.cssClass}`
          return `wave wave-${(getWaveClass() + 1)}`
        })}
      />
    </box>
  )
}
