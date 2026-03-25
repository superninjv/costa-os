import { Gtk } from "ags/gtk4"
import { createState } from "gnim"
import { execAsync } from "ags/process"
import GLib from "gi://GLib"

const STATUS_FILE = "/tmp/ptt-voice-status"
const CMD_FILE = "/tmp/ptt-voice-command"
const LINE_FILE = "/tmp/ptt-voice-lastline"
const OUTPUT_FILE = "/tmp/ptt-voice-output"
const SCROLL_FILE = "/tmp/ptt-voice-scroll"
const MODEL_FILE = "/tmp/ptt-voice-model"

const SPINNER = ["\u280B", "\u2819", "\u2839", "\u2838", "\u283C", "\u2834", "\u2826", "\u2827", "\u2807", "\u280F"]
const MAX_DISPLAY = 50
const WAVE_IDLE_CLASS = "wave-idle"

function readFile(path: string): string {
  try {
    const [ok, contents] = GLib.file_get_contents(path)
    if (ok && contents) return new TextDecoder().decode(contents).trim()
  } catch {}
  return ""
}

interface WaveState {
  text: string
  tooltip: string
  cssClass: string
}

const [getWave, setWave] = createState<WaveState>({
  text: "\uF21E",
  tooltip: "Voice assistant ready (Super+Alt+V)",
  cssClass: "wave-1",
})

let frame = 0
let scrollPos = 0

GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
  const state = readFile(STATUS_FILE) || "idle"
  const cmd = readFile(CMD_FILE).substring(0, 50)
  const lastLine = readFile(LINE_FILE).substring(0, 60)
  const model = readFile(MODEL_FILE)
  const modelTag = model ? `[${model}] ` : ""
  const s = SPINNER[frame % SPINNER.length]
  frame++

  switch (state) {
    case "running": {
      const display = lastLine || cmd
      setWave({
        text: `${s} ${modelTag}${display}`,
        tooltip: `Running: ${cmd}`,
        cssClass: "running",
      })
      break
    }
    case "scroll": {
      const full = readFile(SCROLL_FILE)
      if (full.length <= MAX_DISPLAY) {
        setWave({ text: `\uF001 ${full}`, tooltip: full, cssClass: "scroll" })
      } else {
        const padded = `${full}     \u00B7     ${full}`
        const win = padded.substring(scrollPos, scrollPos + MAX_DISPLAY)
        setWave({ text: `\uF001 ${win}`, tooltip: full, cssClass: "scroll" })
        scrollPos = (scrollPos + 1) % (full.length + 11)
      }
      break
    }
    case "timed out":
      setWave({
        text: "\uF071 timed out",
        tooltip: `Command timed out: ${cmd}`,
        cssClass: "timedout",
      })
      break
    case "interactive":
      setWave({
        text: `${s} \uF059 needs input`,
        tooltip: `Click to focus \u2014 Claude needs clarification\n${cmd}`,
        cssClass: "interactive",
      })
      break
    case "done": {
      const output = readFile(OUTPUT_FILE)
      const summary = output.split("\n").slice(0, 3).join(" ").substring(0, 60)
      setWave({
        text: `\uF00C ${summary}`,
        tooltip: "Click to view full output",
        cssClass: "done",
      })
      break
    }
    default:
      scrollPos = 0
      setWave({
        text: "\uF21E",
        tooltip: "Voice assistant ready (Super+Alt+V)\nClick: open panel  |  Right-click: last output",
        cssClass: WAVE_IDLE_CLASS,
      })
      break
  }

  return GLib.SOURCE_CONTINUE
})

export default function CostaWave() {
  return (
    <button
      class="costa-wave"
      onClicked={() =>
        execAsync("bash -c 'pgrep -f costa-ai-widget/widget.py && killall -f widget.py || python3 ~/.config/costa-ai-widget/widget.py &disown'").catch(() => {})
      }
      tooltipText={getWave.as((w) => w.tooltip)}
    >
      <label
        label={getWave.as((w) => w.text)}
        class={getWave.as((w) => `wave ${w.cssClass}`)}
        maxWidthChars={MAX_DISPLAY}
      />
    </button>
  )
}
