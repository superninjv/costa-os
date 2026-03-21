import { execAsync } from "ags/process"

export default function Power() {
  return (
    <button
      class="power"
      onClicked={() =>
        execAsync("bash -c '~/.config/rofi/powermenu.sh'").catch(() => {})
      }
      tooltipText="Power Menu"
    >
      <label label={"\uF011"} />
    </button>
  )
}
