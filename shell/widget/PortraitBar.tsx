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

// GPU VRAM
function getVram(): string {
  const used = readFile("/sys/class/drm/card1/device/mem_info_vram_used")
  const total = readFile("/sys/class/drm/card1/device/mem_info_vram_total")
  if (!used || !total) return "VRAM: --"
  const usedG = (parseInt(used) / 1073741824).toFixed(1)
  const totalG = (parseInt(total) / 1073741824).toFixed(1)
  return `${usedG}/${totalG}G`
}

// CPU usage
let prevIdle = 0
let prevTotal = 0
function getCpu(): string {
  const stat = readFile("/proc/stat")
  if (!stat) return "CPU: --"
  const line = stat.split("\n")[0]
  const parts = line.split(/\s+/).slice(1).map(Number)
  const idle = parts[3]
  const total = parts.reduce((a, b) => a + b, 0)
  const diffIdle = idle - prevIdle
  const diffTotal = total - prevTotal
  prevIdle = idle
  prevTotal = total
  if (diffTotal === 0) return "CPU: 0%"
  const usage = Math.round((1 - diffIdle / diffTotal) * 100)
  return `CPU: ${usage}%`
}

// RAM
function getRam(): string {
  const meminfo = readFile("/proc/meminfo")
  if (!meminfo) return "RAM: --"
  const lines = meminfo.split("\n")
  let total = 0
  let available = 0
  for (const line of lines) {
    if (line.startsWith("MemTotal:"))
      total = parseInt(line.split(/\s+/)[1])
    if (line.startsWith("MemAvailable:"))
      available = parseInt(line.split(/\s+/)[1])
  }
  const usedG = ((total - available) / 1048576).toFixed(1)
  const totalG = (total / 1048576).toFixed(1)
  return `${usedG}/${totalG}G`
}

const [getVramStr, setVramStr] = createState(getVram())
const [getCpuStr, setCpuStr] = createState(getCpu())
const [getRamStr, setRamStr] = createState(getRam())
const [getClock, setClock] = createState("")

function updateClock() {
  const now = GLib.DateTime.new_now_local()
  setClock(now?.format("%H:%M") ?? "")
}

updateClock()
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => {
  setVramStr(getVram())
  setCpuStr(getCpu())
  setRamStr(getRam())
  updateClock()
  return GLib.SOURCE_CONTINUE
})

const [getWorkspaces, setWorkspaces] = createState(hypr.get_workspaces())
const [getFocused, setFocused] = createState(hypr.get_focused_workspace())

hypr.connect("notify::workspaces", () => setWorkspaces(hypr.get_workspaces()))
hypr.connect("notify::focused-workspace", () => setFocused(hypr.get_focused_workspace()))

function PortraitWorkspaces() {
  const sorted = () =>
    getWorkspaces()
      .filter((ws) => ws.id > 0)
      .sort((a, b) => a.id - b.id)

  return (
    <box class="portrait-workspaces" spacing={4}>
      {sorted().map((ws) => (
        <label
          label={String(ws.id)}
          class={getFocused.as(f => f?.id === ws.id ? "ws-num active" : "ws-num")}
        />
      ))}
    </box>
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
        <box $type="start" spacing={12}>
          <PortraitWorkspaces />
        </box>
        <box $type="center" spacing={16}>
          <label label={getCpuStr.as(v => v)} class="stat" />
          <label label={getRamStr.as(v => v)} class="stat" />
          <label label={getVramStr.as(v => v)} class="stat" tooltipText="GPU VRAM" />
        </box>
        <box $type="end">
          <label label={getClock.as(v => v)} class="portrait-clock" />
        </box>
      </centerbox>
    </window>
  )
}
