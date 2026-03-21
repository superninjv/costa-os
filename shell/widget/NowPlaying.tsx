import { Gtk } from "ags/gtk4"
import { createState } from "gnim"
import { execAsync } from "ags/process"
import Mpris from "gi://AstalMpris"

const mpris = Mpris.get_default()

function truncate(s: string, max: number): string {
  if (s.length <= max) return s
  return s.slice(0, max - 1) + "\u2026"
}

const [getPlayers, setPlayers] = createState(mpris.get_players())
mpris.connect("notify::players", () => setPlayers(mpris.get_players()))

const [getArtist, setArtist] = createState("")
const [getTitle, setTitle] = createState("")

function bindPlayer() {
  const players = mpris.get_players()
  if (players.length > 0) {
    const p = players[0]
    setArtist(p.get_artist() ?? "")
    setTitle(p.get_title() ?? "")
    p.connect("notify::artist", () => setArtist(p.get_artist() ?? ""))
    p.connect("notify::title", () => setTitle(p.get_title() ?? ""))
  }
}

bindPlayer()
mpris.connect("notify::players", bindPlayer)

export default function NowPlaying() {
  return (
    <button
      class="now-playing-btn"
      onClicked={() => {
        execAsync("/usr/bin/python3 /home/jack/.config/music-widget/widget.py").catch(() => {})
      }}
      tooltipText={getTitle.as((t) => t || "Open music player")}
    >
      <label
        label={getTitle.as((t) => {
          if (!t) return "\uF001"
          const a = getArtist()
          const text = a ? `\uF001 ${a} \u2014 ${t}` : `\uF001 ${t}`
          return truncate(text, 35)
        })}
      />
    </button>
  )
}
