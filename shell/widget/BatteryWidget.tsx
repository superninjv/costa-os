import { createState } from "gnim"
import Battery from "gi://AstalBattery"

const bat = Battery.get_default()

function batteryIcon(percent: number, charging: boolean): string {
  if (charging) return "🔌"
  if (percent > 80) return "🔋"
  if (percent > 40) return "🔋"
  if (percent > 15) return "🪫"
  return "🪫"
}

const [getPercentage, setPercentage] = createState(bat.get_percentage())
const [getCharging, setCharging] = createState(bat.get_charging())

bat.connect("notify::percentage", () => setPercentage(bat.get_percentage()))
bat.connect("notify::charging", () => setCharging(bat.get_charging()))

export default function BatteryWidget() {
  return (
    <button
      class={getPercentage.as(p => `battery ${p <= 0.15 ? "battery-low" : ""}`)}
      tooltipText={getPercentage.as(p => {
        const pct = Math.round(p * 100)
        return `${pct}%${getCharging() ? " charging" : ""}`
      })}
    >
      <label
        label={getPercentage.as(p => batteryIcon(Math.round(p * 100), getCharging()))}
      />
    </button>
  )
}
