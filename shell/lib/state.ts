import { createState } from "gnim"
import GLib from "gi://GLib"

const [getBarRevealed, setBarRevealed] = createState(false)
export { getBarRevealed, setBarRevealed }

let hideSource: number | null = null

export function revealBar() {
  if (hideSource !== null) {
    GLib.source_remove(hideSource)
    hideSource = null
  }
  setBarRevealed(true)
  if (barWindow) barWindow.visible = true
}

export function hideBar(delay = 400) {
  if (hideSource !== null) GLib.source_remove(hideSource)
  hideSource = GLib.timeout_add(GLib.PRIORITY_DEFAULT, delay, () => {
    setBarRevealed(false)
    // Hide window after slide-up animation completes
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 350, () => {
      if (!getBarRevealed() && barWindow) barWindow.visible = false
      return GLib.SOURCE_REMOVE
    })
    hideSource = null
    return GLib.SOURCE_REMOVE
  })
}

// Reference to bar window for cleanup on monitor reconnect
let barWindow: any = null
export function setBarWindow(win: any) {
  if (barWindow && barWindow !== win) {
    barWindow.close()
  }
  barWindow = win
}
export function clearBarWindow() {
  barWindow = null
}
