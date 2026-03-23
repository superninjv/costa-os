import { createState } from "gnim"
import { execAsync } from "ags/process"
import Hyprland from "gi://AstalHyprland"

const hypr = Hyprland.get_default()

const [getMonitors, setMonitors] = createState(hypr.get_monitors())
hypr.connect("notify::monitors", () => setMonitors(hypr.get_monitors()))

export default function Headless() {
  return (
    <box
      class="headless"
      visible={getMonitors.as(ms => ms.some((m) => m.get_name().startsWith("HEADLESS")))}
    >
      <button
        class="headless-btn"
        onClicked={() =>
          execAsync("hyprctl dispatch workspace 7").catch(() => {})
        }
        tooltipText="Headless monitor active — click to switch"
      >
        <label label={"\uF108"} class="headless-icon" />
      </button>
    </box>
  )
}
