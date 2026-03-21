import { Gtk } from "ags/gtk4"
import { createState } from "gnim"
import { execAsync } from "ags/process"
import GLib from "gi://GLib"

function parseVolume(output: string): { level: number; muted: boolean } {
  const match = output.match(/Volume:\s+([\d.]+)/)
  const level = match ? parseFloat(match[1]) : 0
  const muted = output.includes("[MUTED]")
  return { level, muted }
}

function volumeIcon(level: number, muted: boolean): string {
  if (muted || level === 0) return "\uF026"
  if (level < 0.33) return "\uF027"
  return "\uF028"
}

const [getVolume, setVolume] = createState({ level: 0, muted: false })

function pollVolume() {
  execAsync("wpctl get-volume @DEFAULT_AUDIO_SINK@")
    .then((out) => setVolume(parseVolume(out)))
    .catch(() => {})
}

pollVolume()
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => {
  pollVolume()
  return GLib.SOURCE_CONTINUE
})

export default function Audio() {
  return (
    <box
      class="audio"
      $={(self: Gtk.Widget) => {
        const scroll = new Gtk.EventControllerScroll()
        scroll.set_flags(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", (_: any, _dx: number, dy: number) => {
          if (dy < 0) {
            execAsync("swayosd-client --output-volume 5").catch(() =>
              execAsync("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+").catch(() => {}),
            )
          } else {
            execAsync("swayosd-client --output-volume -5").catch(() =>
              execAsync("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-").catch(() => {}),
            )
          }
          GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
            pollVolume()
            return GLib.SOURCE_REMOVE
          })
        })
        self.add_controller(scroll)
      }}
    >
      <button
        class={getVolume.as((v) => (v.muted ? "audio-btn muted" : "audio-btn"))}
        onClicked={() => execAsync("pavucontrol").catch(() => {})}
        tooltipText={getVolume.as(
          (v) => `${Math.round(v.level * 100)}%${v.muted ? " (muted)" : ""}`,
        )}
      >
        <label label={getVolume.as((v) => volumeIcon(v.level, v.muted))} />
      </button>
    </box>
  )
}
