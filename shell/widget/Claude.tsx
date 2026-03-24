import { Gtk } from "ags/gtk4"
import { execAsync } from "ags/process"

const LAUNCHER = "~/.config/costa/scripts/claude-launcher.sh"

export default function Claude() {
  return (
    <button
      class="claude"
      onClicked={() =>
        execAsync(`bash -c '${LAUNCHER} project'`).catch(() => {})
      }
      tooltipText="Claude Code\nClick: project picker\nMiddle: dangerous mode\nRight: model picker"
      $={(self: Gtk.Widget) => {
        // Right-click: model picker menu
        const rightClick = new Gtk.GestureClick({ button: 3 })
        rightClick.connect("released", () => {
          execAsync(`bash -c '${LAUNCHER} menu'`).catch(() => {})
        })
        self.add_controller(rightClick)

        // Middle-click: dangerous mode
        const middleClick = new Gtk.GestureClick({ button: 2 })
        middleClick.connect("released", () => {
          execAsync(`bash -c '${LAUNCHER} dangerous'`).catch(() => {})
        })
        self.add_controller(middleClick)
      }}
    >
      <label label={"\uF17B"} />
    </button>
  )
}
