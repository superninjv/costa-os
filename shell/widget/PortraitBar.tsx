import app from "ags/gtk4/app"
import { Astal, Gtk, Gdk } from "ags/gtk4"
import { createState } from "gnim"
import { execAsync } from "ags/process"
import GLib from "gi://GLib"
import Hyprland from "gi://AstalHyprland"

const hypr = Hyprland.get_default()
const { TOP, LEFT, RIGHT } = Astal.WindowAnchor

function readFile(path: string): string {
  try {
    const [ok, contents] = GLib.file_get_contents(path)
    if (ok && contents) return new TextDecoder().decode(contents).trim()
  } catch {}
  return ""
}

function getVram(): string {
  const used = readFile("/sys/class/drm/card1/device/mem_info_vram_used")
  const total = readFile("/sys/class/drm/card1/device/mem_info_vram_total")
  if (!used || !total) return "--"
  const usedG = (parseInt(used) / 1073741824).toFixed(1)
  const totalG = (parseInt(total) / 1073741824).toFixed(1)
  return `${usedG}/${totalG}G`
}

let prevIdle = 0
let prevTotal = 0
function getCpu(): string {
  const stat = readFile("/proc/stat")
  if (!stat) return "--"
  const line = stat.split("\n")[0]
  const parts = line.split(/\s+/).slice(1).map(Number)
  const idle = parts[3]
  const total = parts.reduce((a, b) => a + b, 0)
  const diffIdle = idle - prevIdle
  const diffTotal = total - prevTotal
  prevIdle = idle
  prevTotal = total
  if (diffTotal === 0) return "0%"
  return `${Math.round((1 - diffIdle / diffTotal) * 100)}%`
}

function getRam(): string {
  const meminfo = readFile("/proc/meminfo")
  if (!meminfo) return "--"
  const lines = meminfo.split("\n")
  let total = 0
  let available = 0
  for (const line of lines) {
    if (line.startsWith("MemTotal:")) total = parseInt(line.split(/\s+/)[1])
    if (line.startsWith("MemAvailable:")) available = parseInt(line.split(/\s+/)[1])
  }
  return `${((total - available) / 1048576).toFixed(1)}G`
}

const [getVramStr, setVramStr] = createState(getVram())
const [getCpuStr, setCpuStr] = createState(getCpu())
const [getRamStr, setRamStr] = createState(getRam())
const [getClock, setClock] = createState("")

function updateClock() {
  const now = GLib.DateTime.new_now_local()
  setClock(now?.format("%I:%M") ?? "")
}
updateClock()

GLib.timeout_add(GLib.PRIORITY_DEFAULT, 5000, () => {
  setVramStr(getVram())
  setCpuStr(getCpu())
  setRamStr(getRam())
  updateClock()
  return GLib.SOURCE_CONTINUE
})

function clearChildren(box: Gtk.Box) {
  let child = box.get_first_child()
  while (child) {
    const next = child.get_next_sibling()
    box.remove(child)
    child = next
  }
}

function NumWorkspaces() {
  return (
    <box
      class="portrait-workspaces"
      spacing={2}
      $={(self: Gtk.Box) => {
        const update = () => {
          clearChildren(self)
          const wss = hypr.get_workspaces().filter((ws) => ws.id > 0).sort((a, b) => a.id - b.id)
          const focused = hypr.get_focused_workspace()
          for (const ws of wss) {
            const btn = new Gtk.Button({
              cssClasses: ws.id === focused?.id ? ["ws-num", "active"] : ["ws-num"],
            })
            btn.connect("clicked", () => hypr.dispatch("workspace", String(ws.id)))
            btn.set_child(new Gtk.Label({ label: String(ws.id) }))
            self.append(btn)
          }
        }
        hypr.connect("notify::workspaces", update)
        hypr.connect("notify::focused-workspace", update)
        update()
      }}
    />
  )
}

export default function PortraitBar(gdkmonitor: Gdk.Monitor) {
  return (
    <window
      visible={true}
      name="costa-portrait"
      class="PortraitBar"
      gdkmonitor={gdkmonitor}
      layer={Astal.Layer.TOP}
      anchor={TOP | LEFT | RIGHT}
      exclusivity={Astal.Exclusivity.EXCLUSIVE}
      namespace="costa-portrait"
      application={app}
    >
      <centerbox class="portrait-panel">
        <box $type="start">
          <NumWorkspaces />
        </box>
        <box $type="center" />
        <box $type="end" spacing={4}>
          <button
            class="stat-btn"
            onClicked={() => execAsync("bash -c '~/.config/costa/scripts/toggle-app.sh amdgpu_top amdgpu_top'").catch(() => {})}
            tooltipText="GPU VRAM — click for amdgpu_top"
          >
            <label label={getVramStr.as((v) => v)} class="stat" />
          </button>
          <button
            class="stat-btn"
            onClicked={() => execAsync("bash -c '~/.config/costa/scripts/toggle-app.sh btm btm'").catch(() => {})}
            tooltipText="CPU — click for btm"
          >
            <label label={getCpuStr.as((v) => v)} class="stat" />
          </button>
          <button
            class="stat-btn"
            onClicked={() => execAsync("bash -c '~/.config/costa/scripts/toggle-app.sh btm btm'").catch(() => {})}
            tooltipText="RAM — click for btm"
          >
            <label label={getRamStr.as((v) => v)} class="stat" />
          </button>
          <label label={getClock.as((v) => v)} class="portrait-clock" />
        </box>
      </centerbox>
    </window>
  )
}
