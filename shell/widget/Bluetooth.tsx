import { Gtk } from "ags/gtk4"
import { createState } from "gnim"
import { execAsync } from "ags/process"
import GLib from "gi://GLib"
import { lockBar, unlockBar } from "../lib/state"

function sq(s: string): string { return GLib.shell_quote(s) }

interface BtDevice {
  mac: string
  name: string
  connected: boolean
  paired: boolean
  icon: string
}

interface BtState {
  powered: boolean
  scanning: boolean
  devices: BtDevice[]
  connectedName: string
  operatingMac: string
}

const [getBt, setBt] = createState<BtState>({
  powered: false,
  scanning: false,
  devices: [],
  connectedName: "",
  operatingMac: "",
})

function isValidMac(mac: string): boolean {
  return /^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$/.test(mac)
}

function deviceIcon(name: string, mac: string): string {
  const n = name.toLowerCase()
  if (n.includes("airpods") || n.includes("headphone") || n.includes("buds") || n.includes("earbuds") || n.includes("wh-") || n.includes("wf-")) return "\uF025"
  if (n.includes("speaker") || n.includes("soundbar") || n.includes("jbl") || n.includes("ue ")) return "\uF028"
  if (n.includes("keyboard") || n.includes("keychron") || n.includes("hhkb")) return "\uF11C"
  if (n.includes("mouse") || n.includes("trackpad") || n.includes("mx ")) return "\uF245"
  if (n.includes("phone") || n.includes("iphone") || n.includes("pixel") || n.includes("galaxy") || n.includes("samsung")) return "\uF3CD"
  if (n.includes("watch") || n.includes("band")) return "\uF017"
  if (n.includes("controller") || n.includes("gamepad") || n.includes("dualsense") || n.includes("xbox")) return "\uF11B"
  return "\uF293"
}

function deviceDisplayName(name: string, mac: string): string {
  if (!name || name === mac || /^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$/.test(name)) return `Unknown (${mac.slice(-8)})`
  // Strip " - Find My" suffix Apple adds
  return name.replace(/ - Find My$/, "")
}

// ─── Polling ────────────────────────────────────────

function pollBt() {
  execAsync("bash -c \"bluetoothctl show | grep -q 'Powered: yes' && echo powered || echo off\"")
    .then((out) => {
      const powered = out.trim() === "powered"
      if (powered) {
        execAsync("bash -c \"bluetoothctl devices Connected | head -1 | cut -d' ' -f3-\"")
          .then((dev) => setBt({ ...getBt(), powered, connectedName: deviceDisplayName(dev.trim(), "") }))
          .catch(() => setBt({ ...getBt(), powered, connectedName: "" }))
      } else {
        setBt({ ...getBt(), powered, connectedName: "", devices: [] })
      }
    })
    .catch(() => setBt({ ...getBt(), powered: false, connectedName: "" }))
}

function refreshDevices() {
  execAsync("bash -c \"bluetoothctl devices\"")
    .then((out) => {
      const connP = execAsync("bash -c \"bluetoothctl devices Connected 2>/dev/null || true\"")
      const pairP = execAsync("bash -c \"bluetoothctl devices Paired 2>/dev/null || true\"")
      Promise.all([connP, pairP])
        .then(([connOut, pairedOut]) => {
          const connMacs = new Set(connOut.trim().split("\n").filter(Boolean).map((l) => l.split(" ")[1]))
          const pairMacs = new Set(pairedOut.trim().split("\n").filter(Boolean).map((l) => l.split(" ")[1]))
          const seen = new Set<string>()
          const devs: BtDevice[] = []
          for (const line of out.trim().split("\n")) {
            if (!line) continue
            const parts = line.split(" ")
            if (parts.length < 3) continue
            const mac = parts[1]
            const rawName = parts.slice(2).join(" ")
            if (!mac || seen.has(mac)) continue
            seen.add(mac)
            const name = deviceDisplayName(rawName, mac)
            devs.push({
              mac, name,
              connected: connMacs.has(mac),
              paired: pairMacs.has(mac),
              icon: deviceIcon(rawName, mac),
            })
          }
          devs.sort((a, b) => {
            if (a.connected && !b.connected) return -1
            if (!a.connected && b.connected) return 1
            if (a.paired && !b.paired) return -1
            if (!a.paired && b.paired) return 1
            return a.name.localeCompare(b.name)
          })
          setBt({ ...getBt(), devices: devs })
        })
        .catch(() => {})
    })
    .catch(() => {})
}

let scanTimers: number[] = []

function scanDevices() {
  const bt = getBt()
  if (!bt.powered || bt.scanning) return
  setBt({ ...bt, scanning: true })

  for (const id of scanTimers) GLib.source_remove(id)
  scanTimers = []

  execAsync("bluetoothctl scan on").catch(() => {})
  refreshDevices()

  scanTimers.push(GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => { refreshDevices(); return GLib.SOURCE_REMOVE }))
  scanTimers.push(GLib.timeout_add(GLib.PRIORITY_DEFAULT, 4000, () => {
    execAsync("bluetoothctl scan off").catch(() => {})
    return GLib.SOURCE_REMOVE
  }))
  scanTimers.push(GLib.timeout_add(GLib.PRIORITY_DEFAULT, 4500, () => {
    refreshDevices()
    setBt({ ...getBt(), scanning: false })
    scanTimers = []
    return GLib.SOURCE_REMOVE
  }))
}

function handleDevice(mac: string, isPaired: boolean, isConnected: boolean) {
  if (getBt().operatingMac || !isValidMac(mac)) return
  setBt({ ...getBt(), operatingMac: mac })
  let cmd: string
  if (isConnected) cmd = `bluetoothctl disconnect ${sq(mac)}`
  else if (isPaired) cmd = `bluetoothctl connect ${sq(mac)}`
  else cmd = `bash -c "bluetoothctl pair ${sq(mac)} && bluetoothctl trust ${sq(mac)} && bluetoothctl connect ${sq(mac)}"`

  execAsync(cmd)
    .then(() => {
      GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1500, () => {
        pollBt()
        refreshDevices()
        // Auto-switch audio to this device if it's an audio device
        if (!isConnected) trySetAudioSink(mac)
        return GLib.SOURCE_REMOVE
      })
    })
    .catch(() => {})
    .finally(() => {
      setBt({ ...getBt(), operatingMac: "" })
    })
}

function forgetDevice(mac: string) {
  if (!isValidMac(mac)) return
  execAsync(`bluetoothctl remove ${sq(mac)}`).catch(() => {})
  GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => { refreshDevices(); return GLib.SOURCE_REMOVE })
}

function togglePower() {
  const bt = getBt()
  execAsync(`bluetoothctl power ${bt.powered ? "off" : "on"}`).catch(() => {})
  GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => { pollBt(); return GLib.SOURCE_REMOVE })
}

function trySetAudioSink(mac: string) {
  // Check if this BT device has an audio sink and switch to it
  const cardName = `bluez_card.${mac.replace(/:/g, "_")}`
  execAsync(`bash -c "pactl list cards short | grep ${sq(cardName)}"`)
    .then(() => {
      // Try A2DP first, fall back to whatever is available
      execAsync(`pactl set-card-profile ${sq(cardName)} a2dp-sink`).catch(() => {
        execAsync(`pactl set-card-profile ${sq(cardName)} a2dp-sink-aac`).catch(() => {
          execAsync(`pactl set-card-profile ${sq(cardName)} a2dp-sink-sbc`).catch(() => {})
        })
      })
      // Set as default sink
      GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
        const sinkName = `bluez_output.${mac.replace(/:/g, "_")}.1`
        execAsync(`wpctl set-default $(bash -c "wpctl status | grep -i '${mac.replace(/:/g, "_")}' | grep -oP '\\d+\\.' | head -1 | tr -d '.'") 2>/dev/null`).catch(() => {})
        return GLib.SOURCE_REMOVE
      })
    })
    .catch(() => {}) // Not an audio device
}

// ─── Init ────────────────────────────────────────

pollBt()
refreshDevices()
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 5000, () => { pollBt(); return GLib.SOURCE_CONTINUE })

// ─── Components ──────────────────────────────────

function DeviceRow({ dev }: { dev: BtDevice }) {
  const bt = getBt()
  const isOperating = bt.operatingMac === dev.mac
  const statusLabel = dev.connected ? "Connected" : dev.paired ? "Paired" : "New"
  const statusClass = dev.connected ? "bt-status-connected" : dev.paired ? "bt-status-paired" : "bt-status-new"

  return (
    <box class={`bt-device ${dev.connected ? "connected" : ""}`} spacing={0}>
      <button
        class="bt-device-main"
        hexpand={true}
        sensitive={!isOperating}
        onClicked={() => handleDevice(dev.mac, dev.paired, dev.connected)}
      >
        <box spacing={10}>
          <label class="bt-device-icon" label={dev.icon} />
          <box orientation={Gtk.Orientation.VERTICAL} hexpand={true}>
            <label class="bt-device-name" label={isOperating ? `${dev.name}...` : dev.name} xalign={0} />
            <label class={`bt-device-status ${statusClass}`} label={statusLabel} xalign={0} />
          </box>
        </box>
      </button>
      {dev.paired ? (
        <button
          class="bt-device-forget"
          tooltipText="Forget"
          onClicked={() => forgetDevice(dev.mac)}
        >
          <label label={"\uF1F8"} />
        </button>
      ) : <box />}
    </box>
  )
}

export default function Bluetooth() {
  return (
    <menubutton
      class={getBt.as((bt) => bt.powered ? (bt.connectedName ? "bt-btn connected" : "bt-btn") : "bt-btn off")}
      tooltipText={getBt.as((bt) =>
        bt.powered
          ? (bt.connectedName ? `${bt.connectedName}` : "Bluetooth")
          : "Bluetooth off"
      )}
      $={(self: Gtk.MenuButton) => {
        const popover = self.get_popover()
        if (popover) {
          popover.connect("notify::visible", () => {
            if (popover.visible) {
              lockBar()
              if (getBt().powered) { refreshDevices(); scanDevices() }
            } else {
              unlockBar()
            }
          })
        }
      }}
    >
      <label label={getBt.as((bt) => bt.powered ? "\uF293" : "\uF294")} />
      <popover>
        <box orientation={Gtk.Orientation.VERTICAL} class="bt-popup" widthRequest={280} spacing={6}>
          {/* Header */}
          <box class="bt-header" spacing={8}>
            <label class="bt-title" label="Bluetooth" hexpand={true} xalign={0} />
            <button
              class="bt-scan-btn"
              onClicked={() => scanDevices()}
              tooltipText="Scan for devices"
              sensitive={getBt.as((bt) => bt.powered && !bt.scanning)}
            >
              <label label={getBt.as((bt) => bt.scanning ? "\uF110" : "\uF002")} />
            </button>
            <Gtk.Switch
              active={getBt.as((bt) => bt.powered)}
              valign={Gtk.Align.CENTER}
              onStateSet={(self: Gtk.Switch, state: boolean) => {
                if (state !== getBt().powered) togglePower()
                return false
              }}
            />
          </box>

          {/* Device list */}
          <Gtk.ScrolledWindow
            vexpand={true}
            hscrollbarPolicy={Gtk.PolicyType.NEVER}
            maxContentHeight={300}
            propagateNaturalHeight={true}
          >
            <box orientation={Gtk.Orientation.VERTICAL} class="bt-list" spacing={2}>
              {getBt.as((bt) => {
                if (!bt.powered) return [<label class="bt-empty" label="Bluetooth is off" />]
                if (bt.devices.length === 0) return [<label class="bt-empty" label={bt.scanning ? "Scanning..." : "No devices found"} />]
                return bt.devices.map((dev) => <DeviceRow dev={dev} />)
              })}
            </box>
          </Gtk.ScrolledWindow>
        </box>
      </popover>
    </menubutton>
  )
}
