import { createState } from "gnim"
import GLib from "gi://GLib"

const [getBarRevealed, setBarRevealed] = createState(false)
export { getBarRevealed, setBarRevealed }

let hideSource: number | null = null
let barLocked = false

export function lockBar() { barLocked = true; revealBar() }
export function unlockBar() { barLocked = false; hideBar(1200) }

export function revealBar() {
  if (hideSource !== null) {
    GLib.source_remove(hideSource)
    hideSource = null
  }
  setBarRevealed(true)
  if (barWindow) barWindow.visible = true
}

export function hideBar(delay = 400) {
  if (barLocked) return
  if (hideSource !== null) GLib.source_remove(hideSource)
  hideSource = GLib.timeout_add(GLib.PRIORITY_DEFAULT, delay, () => {
    if (barLocked) { hideSource = null; return GLib.SOURCE_REMOVE }
    setBarRevealed(false)
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 350, () => {
      if (!getBarRevealed() && barWindow) barWindow.visible = false
      return GLib.SOURCE_REMOVE
    })
    hideSource = null
    return GLib.SOURCE_REMOVE
  })
}

// Reference to bar window for show/hide
let barWindow: any = null
export function setBarWindow(win: any) {
  // If replacing an existing bar (monitor reconnect), clean up old state
  if (barWindow && barWindow !== win) {
    barWindow.visible = false
  }
  barWindow = win
  win.visible = false
}
export function clearBarWindow() {
  barWindow = null
}
