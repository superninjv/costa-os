import { execAsync } from "ags/process"

export default function Power() {
  return (
    <button
      class="power"
      onClicked={() =>
        execAsync(`bash -c 'choice=$(printf "Lock\\nLogout\\nSuspend\\nReboot\\nShutdown" | rofi -dmenu -p "Power" -i -theme-str "window {width: 200px;}"); case "$choice" in Lock) hyprctl dispatch exec loginctl lock-session;; Logout) hyprctl dispatch exit;; Suspend) systemctl suspend;; Reboot) systemctl reboot;; Shutdown) systemctl poweroff;; esac'`).catch(() => {})
      }
      tooltipText="Power Menu"
    >
      <label label={"\uF011"} />
    </button>
  )
}
