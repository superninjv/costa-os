import { createState } from "gnim"
import { execAsync, exec } from "ags/process"
import Hyprland from "gi://AstalHyprland"

const hypr = Hyprland.get_default()

const [getMonitors, setMonitors] = createState(hypr.get_monitors())
hypr.connect("notify::monitors", () => setMonitors(hypr.get_monitors()))

let mirrorActive = false

function toggleMirror() {
  if (mirrorActive) {
    execAsync("pkill -f 'wl-mirror HEADLESS-2'").catch(() => {})
    mirrorActive = false
  } else {
    // Launch wl-mirror as a floating PIP window, Hyprland rules handle placement
    execAsync("wl-mirror HEADLESS-2").catch(() => {})
    mirrorActive = true
  }
}

export default function Headless() {
  return (
    <box
      class="headless"
      visible={getMonitors.as(ms => ms.some((m) => m.get_name().startsWith("HEADLESS")))}
    >
      <button
        class="headless-btn"
        onClicked={toggleMirror}
        tooltipText="Toggle Claude's headless monitor overlay"
      >
        <label label={"\uF108"} class="headless-icon" />
      </button>
    </box>
  )
}
