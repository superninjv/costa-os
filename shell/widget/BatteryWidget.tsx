import { createState } from "gnim"
import Battery from "gi://AstalBattery"

const bat = Battery.get_default()

function batteryIcon(percent: number, charging: boolean): string {
  if (charging) return "\uF1E6"
  if (percent > 80) return "\uF240"
  if (percent > 60) return "\uF241"
  if (percent > 40) return "\uF242"
  if (percent > 15) return "\uF243"
  return "\uF244"
}

// Guard against battery service being unavailable (desktops, VMs)
const hasBattery = bat != null
const [getPercentage, setPercentage] = createState(hasBattery ? bat.get_percentage() : 0)
const [getCharging, setCharging] = createState(hasBattery ? bat.get_charging() : false)
const [getIsPresent, setIsPresent] = createState(hasBattery ? bat.get_is_present() : false)

if (hasBattery) {
  bat.connect("notify::percentage", () => setPercentage(bat.get_percentage()))
  bat.connect("notify::charging", () => setCharging(bat.get_charging()))
  bat.connect("notify::is-present", () => setIsPresent(bat.get_is_present()))
}

export default function BatteryWidget() {
  return (
    <button
      class={getPercentage.as((p) => `battery ${p <= 0.15 ? "battery-low" : ""}`)}
      visible={getIsPresent.as((p) => p)}
      tooltipText={getPercentage.as((p) => {
        const pct = Math.round(p * 100)
        return `${pct}%${getCharging() ? " charging" : ""}`
      })}
    >
      <label
        label={getPercentage.as((p) => batteryIcon(Math.round(p * 100), getCharging()))}
      />
    </button>
  )
}
