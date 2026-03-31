import { Gtk } from "ags/gtk4"
import { createState } from "gnim"
import { execAsync } from "ags/process"
import GLib from "gi://GLib"

const LICENSE_FILE = GLib.get_home_dir() + "/.config/costa/license"

function isLicensed(): boolean {
  try {
    const [ok, contents] = GLib.file_get_contents(LICENSE_FILE)
    if (!ok || !contents) return false
    const data = JSON.parse(new TextDecoder().decode(contents))
    return typeof data.key === "string" && data.key.startsWith("COSTA-")
  } catch {
    return false
  }
}

const [getLicensed, setLicensed] = createState(isLicensed())

// Re-check license every 60s (in case user activates mid-session)
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 60000, () => {
  setLicensed(isLicensed())
  return GLib.SOURCE_CONTINUE
})

export default function CostaBadge() {
  return (
    <button
      visible={getLicensed.as((v) => !v)}
      class="costa-badge"
      tooltipText="Costa OS Free — click to support ($9.99)"
      onClicked={() =>
        execAsync("xdg-open https://synoros.io/costa-os#pro").catch(() => {})
      }
    >
      <label label="Costa" />
    </button>
  )
}
