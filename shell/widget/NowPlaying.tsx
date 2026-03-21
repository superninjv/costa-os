import { createState } from "gnim"
import Mpris from "gi://AstalMpris"
import GLib from "gi://GLib"

const mpris = Mpris.get_default()

function truncate(s: string, max: number): string {
  if (s.length <= max) return s
  return s.slice(0, max - 1) + "\u2026"
}

const [getPlayers, setPlayers] = createState(mpris.get_players())
mpris.connect("notify::players", () => setPlayers(mpris.get_players()))

export default function NowPlaying() {
  const players = getPlayers()

  if (players.length === 0) {
    return <box class="now-playing" />
  }

  const player = players[0]
  const [getArtist, setArtist] = createState(player.get_artist() ?? "")
  const [getTitle, setTitle] = createState(player.get_title() ?? "")

  player.connect("notify::artist", () => setArtist(player.get_artist() ?? ""))
  player.connect("notify::title", () => setTitle(player.get_title() ?? ""))

  const displayText = () => {
    const t = getTitle()
    const a = getArtist()
    if (!t) return ""
    const text = a ? `\u266A ${a} \u2014 ${t}` : `\u266A ${t}`
    return truncate(text, 40)
  }

  return (
    <box class="now-playing">
      <button
        onClicked={() => player.play_pause()}
        class="now-playing-btn"
      >
        <label label={displayText()} />
      </button>
    </box>
  )
}
