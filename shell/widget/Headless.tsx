import { createState } from "gnim"
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
      <label
        label="🖥"
        class="headless-icon"
        tooltipText="Headless monitor active"
      />
    </box>
  )
}
