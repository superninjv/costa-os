import { Gtk } from "ags/gtk4"
import { createState } from "gnim"
import { execAsync } from "ags/process"
import GLib from "gi://GLib"

interface BtDevice {
  mac: string
  name: string
  connected: boolean
  paired: boolean
}

interface BtState {
  powered: boolean
  connected: string
  devices: BtDevice[]
  scanning: boolean
  connectingMac: string
}

const [getBt, setBt] = createState<BtState>({
  powered: false,
  connected: "",
  devices: [],
  scanning: false,
  connectingMac: "",
})

function pollBt() {
  execAsync("bash -c \"bluetoothctl show | grep -q 'Powered: yes' && echo powered || echo off\"")
    .then((out) => {
      const powered = out.trim() === "powered"
      if (powered) {
        execAsync("bash -c \"bluetoothctl devices Connected | head -1 | cut -d' ' -f3-\"")
          .then((dev) => setBt({ ...getBt(), powered: true, connected: dev.trim() }))
          .catch(() => setBt({ ...getBt(), powered: true, connected: "" }))
      } else {
        setBt({ ...getBt(), powered: false, connected: "" })
      }
    })
    .catch(() => setBt({ ...getBt(), powered: false, connected: "" }))
}

function scanDevices() {
  const state = getBt()
  if (!state.powered) return

  setBt({ ...getBt(), scanning: true })

  // Start scan briefly
  execAsync("bluetoothctl scan on").catch(() => {})

  // Stop scan after 4 seconds and collect results
  GLib.timeout_add(GLib.PRIORITY_DEFAULT, 4000, () => {
    execAsync("bluetoothctl scan off").catch(() => {})
    return GLib.SOURCE_REMOVE
  })

  // Gather paired + available devices
  execAsync("bash -c \"bluetoothctl devices\"")
    .then((out) => {
      const connectedPromise = execAsync("bash -c \"bluetoothctl devices Connected 2>/dev/null || true\"")
      const pairedPromise = execAsync("bash -c \"bluetoothctl devices Paired 2>/dev/null || true\"")

      Promise.all([connectedPromise, pairedPromise])
        .then(([connOut, pairedOut]) => {
          const connectedMacs = new Set(
            connOut.trim().split("\n").filter(Boolean).map((l) => l.split(" ")[1])
          )
          const pairedMacs = new Set(
            pairedOut.trim().split("\n").filter(Boolean).map((l) => l.split(" ")[1])
          )

          const seen = new Set<string>()
          const devices: BtDevice[] = []

          for (const line of out.trim().split("\n")) {
            if (!line) continue
            const parts = line.split(" ")
            if (parts.length < 3) continue
            const mac = parts[1]
            const name = parts.slice(2).join(" ")
            if (!mac || seen.has(mac)) continue
            // Skip unnamed devices
            if (name === mac || name.startsWith("00:") || name.startsWith("FF:")) continue
            seen.add(mac)
            devices.push({
              mac,
              name,
              connected: connectedMacs.has(mac),
              paired: pairedMacs.has(mac),
            })
          }

          // Connected first, then paired, then others
          devices.sort((a, b) => {
            if (a.connected && !b.connected) return -1
            if (!a.connected && b.connected) return 1
            if (a.paired && !b.paired) return -1
            if (!a.paired && b.paired) return 1
            return a.name.localeCompare(b.name)
          })

          setBt({ ...getBt(), devices, scanning: false })
        })
        .catch(() => setBt({ ...getBt(), scanning: false }))
    })
    .catch(() => setBt({ ...getBt(), scanning: false }))
}

function toggleDevice(mac: string, currentlyConnected: boolean) {
  setBt({ ...getBt(), connectingMac: mac })
  const cmd = currentlyConnected ? "disconnect" : "connect"
  execAsync(`bluetoothctl ${cmd} ${mac}`)
    .then(() => {
      setBt({ ...getBt(), connectingMac: "" })
      GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
        pollBt()
        scanDevices()
        return GLib.SOURCE_REMOVE
      })
    })
    .catch(() => {
      setBt({ ...getBt(), connectingMac: "" })
    })
}

function togglePower() {
  const state = getBt()
  const cmd = state.powered ? "power off" : "power on"
  execAsync(`bluetoothctl ${cmd}`).catch(() => {})
  GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
    pollBt()
    return GLib.SOURCE_REMOVE
  })
}

pollBt()
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 5000, () => {
  pollBt()
  return GLib.SOURCE_CONTINUE
})

function DeviceItem({ dev }: { dev: BtDevice }) {
  const state = getBt()
  const isConnecting = state.connectingMac === dev.mac
  const icon = dev.connected ? "\uF293" : dev.paired ? "\uF294" : "\uF294"

  return (
    <button
      class={`bt-dev-item ${dev.connected ? "connected" : ""}`}
      onClicked={() => toggleDevice(dev.mac, dev.connected)}
      sensitive={!isConnecting}
      tooltipText={dev.connected ? "Click to disconnect" : dev.paired ? "Click to connect" : "Click to connect"}
    >
      <box spacing={8}>
        <label class="bt-dev-icon" label={icon} />
        <label
          class="bt-dev-name"
          label={isConnecting ? `${dev.name}...` : dev.name}
          hexpand={true}
          xalign={0}
        />
        {dev.connected ? (
          <label class="bt-dev-check" label={"\uF00C"} />
        ) : dev.paired ? (
          <label class="bt-dev-paired" label="paired" />
        ) : (
          <box />
        )}
      </box>
    </button>
  )
}

export default function Bluetooth() {
  return (
    <menubutton
      class={getBt.as((b) => {
        if (!b.powered) return "bt-btn off"
        return b.connected ? "bt-btn connected" : "bt-btn on"
      })}
      tooltipText={getBt.as((b) => {
        if (!b.powered) return "Bluetooth off"
        return b.connected ? `Connected: ${b.connected}` : "Bluetooth on (no device)"
      })}
      onActivate={() => {
        if (getBt().powered) scanDevices()
      }}
    >
      <label label={getBt.as((b) => b.powered ? "\uF293" : "\uF294")} />
      <popover>
        <box vertical={true} class="bt-popup" widthRequest={260}>
          <box class="bt-header" spacing={8}>
            <label class="bt-title" label="Bluetooth" hexpand={true} xalign={0} />
            <button
              class="bt-scan"
              onClicked={() => scanDevices()}
              tooltipText="Scan"
              sensitive={getBt.as((b) => b.powered && !b.scanning)}
            >
              <label label={getBt.as((b) => b.scanning ? "\uF110" : "\uF002")} />
            </button>
            <button
              class={getBt.as((b) => b.powered ? "bt-power on" : "bt-power")}
              onClicked={() => togglePower()}
              tooltipText={getBt.as((b) => b.powered ? "Turn off" : "Turn on")}
            >
              <label label={"\uF011"} />
            </button>
          </box>
          <Gtk.ScrolledWindow
            vexpand={true}
            hscrollbarPolicy={Gtk.PolicyType.NEVER}
            maxContentHeight={250}
            propagateNaturalHeight={true}
          >
            <box vertical={true} class="bt-list" spacing={2}>
              {getBt.as((b) => {
                if (!b.powered) return [<label class="bt-empty" label="Bluetooth is off" />]
                if (b.devices.length === 0)
                  return [<label class="bt-empty" label={b.scanning ? "Scanning..." : "No devices found"} />]
                return b.devices.map((dev) => <DeviceItem dev={dev} />)
              })}
            </box>
          </Gtk.ScrolledWindow>
        </box>
      </popover>
    </menubutton>
  )
}
