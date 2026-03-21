import { createState } from "gnim"
import { execAsync } from "ags/process"
import Hyprland from "gi://AstalHyprland"
import GLib from "gi://GLib"

const hypr = Hyprland.get_default()

interface GitState {
  branch: string
  dirty: boolean
  visible: boolean
}

const [getGitState, setGitState] = createState<GitState>({ branch: "", dirty: false, visible: false })

function detectProjectDir(): string | null {
  const client = hypr.get_focused_client()
  if (!client) return null

  const title = client.get_title()
  if (!title) return null

  // Try to extract path from terminal/editor titles
  const homeMatch = title.match(/~\/([^\s]+)/)
  if (homeMatch) {
    const home = GLib.get_home_dir()
    return `${home}/${homeMatch[1]}`
  }

  const absMatch = title.match(/(\/[^\s]+)/)
  if (absMatch) return absMatch[1]

  return null
}

function pollGit() {
  const dir = detectProjectDir()
  if (!dir) {
    setGitState({ branch: "", dirty: false, visible: false })
    return
  }

  execAsync(`git -C ${dir} rev-parse --git-dir`)
    .then(() => {
      return Promise.all([
        execAsync(`git -C ${dir} symbolic-ref --short HEAD`).catch(() => "detached"),
        execAsync(`git -C ${dir} status --porcelain`).catch(() => ""),
      ])
    })
    .then(([branch, status]) => {
      setGitState({
        branch: branch.trim(),
        dirty: status.trim().length > 0,
        visible: true,
      })
    })
    .catch(() => {
      setGitState({ branch: "", dirty: false, visible: false })
    })
}

pollGit()
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 10000, () => {
  pollGit()
  return GLib.SOURCE_CONTINUE
})

export default function Git() {
  return (
    <box
      class="git"
      visible={getGitState.as(s => s.visible)}
    >
      <label
        class={getGitState.as(s => `git-icon ${s.dirty ? "dirty" : "clean"}`)}
        label={"\uE725"}
        tooltipText={getGitState.as(s => `${s.branch}${s.dirty ? " (dirty)" : ""}`)}
      />
    </box>
  )
}
