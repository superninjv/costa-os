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
  if (barWindow) {
    barWindow.visible = true
    barWindow.present()
  }
}

export function hideBar(delay = 400) {
  if (barLocked) return
  if (hideSource !== null) GLib.source_remove(hideSource)
  hideSource = GLib.timeout_add(GLib.PRIORITY_DEFAULT, delay, () => {
    if (barLocked) { hideSource = null; return GLib.SOURCE_REMOVE }
    setBarRevealed(false)
    hideSource = null
    return GLib.SOURCE_REMOVE
  })
}

// Reference to bar window for cleanup on monitor reconnect
let barWindow: any = null
let barRevealer: any = null
export function setBarRevealer(rev: any) {
  if (barRevealer) return // already connected
  barRevealer = rev
  // Hide window the instant the revealer animation finishes
  rev.connect("notify::child-revealed", () => {
    if (!rev.get_child_revealed() && barWindow) {
      barWindow.visible = false
    }
  })
}
export function setBarWindow(win: any) {
  if (barWindow && barWindow !== win) {
    barWindow.close()
  }
  barWindow = win
}
export function clearBarWindow() {
  barWindow = null
}
