import { Gtk } from "ags/gtk4"
import { createState } from "gnim"
import { execAsync } from "ags/process"
import GLib from "gi://GLib"

function sq(s: string): string { return GLib.shell_quote(s) }

interface WifiNetwork {
  ssid: string
  signal: number
  security: string
  active: boolean
}

interface WifiState {
  connected: boolean
  ssid: string
  signal: number
  networks: WifiNetwork[]
  scanning: boolean
  connectingSsid: string
  showPassword: boolean
  passwordSsid: string
}

const [getWifi, setWifi] = createState<WifiState>({
  connected: false,
  ssid: "",
  signal: 0,
  networks: [],
  scanning: false,
  connectingSsid: "",
  showPassword: false,
  passwordSsid: "",
})

function wifiIcon(state: WifiState): string {
  if (!state.connected) return "\uF1EB"
  return "\uF1EB"
}

function signalIcon(signal: number): string {
  if (signal > 75) return "\uF1EB"
  if (signal > 50) return "\uF1EB"
  if (signal > 25) return "\uF1EB"
  return "\uF1EB"
}

function pollWifi() {
  execAsync("bash -c \"nmcli -t -f ACTIVE,SSID,SIGNAL dev wifi | grep '^yes' | head -1\"")
    .then((out) => {
      const parts = out.trim().split(":")
      if (parts.length >= 3) {
        setWifi({ ...getWifi(), connected: true, ssid: parts[1], signal: parseInt(parts[2]) || 0 })
      } else {
        setWifi({ ...getWifi(), connected: false, ssid: "", signal: 0 })
      }
    })
    .catch(() => setWifi({ ...getWifi(), connected: false, ssid: "", signal: 0 }))
}

function scanNetworks() {
  setWifi({ ...getWifi(), scanning: true })
  execAsync("bash -c \"nmcli -t -f ACTIVE,SSID,SIGNAL,SECURITY dev wifi list --rescan yes 2>/dev/null\"")
    .then((out) => {
      const seen = new Set<string>()
      const networks: WifiNetwork[] = []
      for (const line of out.trim().split("\n")) {
        if (!line) continue
        const parts = line.split(":")
        if (parts.length < 4) continue
        const ssid = parts[1]
        if (!ssid || seen.has(ssid)) continue
        seen.add(ssid)
        networks.push({
          ssid,
          signal: parseInt(parts[2]) || 0,
          security: parts[3] || "",
          active: parts[0] === "yes",
        })
      }
      networks.sort((a, b) => {
        if (a.active && !b.active) return -1
        if (!a.active && b.active) return 1
        return b.signal - a.signal
      })
      setWifi({ ...getWifi(), networks, scanning: false })
    })
    .catch(() => setWifi({ ...getWifi(), scanning: false }))
}

function connectToNetwork(ssid: string) {
  // Try connecting (works for known/saved networks)
  setWifi({ ...getWifi(), connectingSsid: ssid })
  execAsync(`nmcli dev wifi connect ${sq(ssid)}`)
    .then(() => {
      setWifi({ ...getWifi(), connectingSsid: "" })
      pollWifi()
      scanNetworks()
    })
    .catch((err) => {
      const errStr = String(err)
      if (errStr.includes("Secrets were required") || errStr.includes("No suitable connection")) {
        setWifi({ ...getWifi(), connectingSsid: "", showPassword: true, passwordSsid: ssid })
      } else {
        setWifi({ ...getWifi(), connectingSsid: "" })
      }
    })
}

function connectWithPassword(ssid: string, password: string) {
  setWifi({ ...getWifi(), connectingSsid: ssid, showPassword: false, passwordSsid: "" })
  execAsync(`nmcli dev wifi connect ${sq(ssid)} password ${sq(password)}`)
    .then(() => {
      setWifi({ ...getWifi(), connectingSsid: "" })
      pollWifi()
      scanNetworks()
    })
    .catch(() => {
      setWifi({ ...getWifi(), connectingSsid: "" })
    })
}

function disconnectWifi() {
  execAsync("nmcli -t -f DEVICE,TYPE dev")
    .then((out) => {
      const wifiLine = out.trim().split("\n").find((l) => l.endsWith(":wifi"))
      if (wifiLine) {
        const iface = wifiLine.split(":")[0]
        if (/^[a-zA-Z0-9_-]+$/.test(iface)) return execAsync(`nmcli dev disconnect ${iface}`)
      }
    })
    .catch(() => {})
  GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
    pollWifi()
    scanNetworks()
    return GLib.SOURCE_REMOVE
  })
}

pollWifi()
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 5000, () => {
  pollWifi()
  return GLib.SOURCE_CONTINUE
})

function NetworkItem({ net }: { net: WifiNetwork }) {
  const state = getWifi()
  const isConnecting = state.connectingSsid === net.ssid
  return (
    <button
      class={`wifi-net-item ${net.active ? "active" : ""}`}
      onClicked={() => {
        if (net.active) {
          disconnectWifi()
        } else {
          connectToNetwork(net.ssid)
        }
      }}
      sensitive={!isConnecting}
    >
      <box spacing={8}>
        <label class="wifi-net-signal" label={signalIcon(net.signal)} />
        <label
          class="wifi-net-name"
          label={isConnecting ? `${net.ssid}...` : net.ssid}
          hexpand={true}
          xalign={0}
        />
        {net.security && net.security !== "--" ? (
          <label class="wifi-net-lock" label={"\uF023"} />
        ) : (
          <box />
        )}
        {net.active ? (
          <label class="wifi-net-check" label={"\uF00C"} />
        ) : (
          <box />
        )}
      </box>
    </button>
  )
}

function PasswordEntry() {
  const state = getWifi()
  if (!state.showPassword) return <box />

  return (
    <box class="wifi-password-box" orientation={Gtk.Orientation.VERTICAL} spacing={6}>
      <label class="wifi-password-label" label={`Password for ${state.passwordSsid}`} xalign={0} />
      <box spacing={6}>
        <entry
          class="wifi-password-entry"
          placeholderText="Enter password..."
          visibility={false}
          hexpand={true}
          onActivate={(self: Gtk.Entry) => {
            const pw = self.get_text()
            if (pw) connectWithPassword(state.passwordSsid, pw)
          }}
        />
        <button
          class="wifi-password-cancel"
          onClicked={() => setWifi({ ...getWifi(), showPassword: false, passwordSsid: "" })}
        >
          <label label={"\uF00D"} />
        </button>
      </box>
    </box>
  )
}

export default function Wifi() {
  return (
    <menubutton
      class={getWifi.as((w) => w.connected ? "wifi-btn connected" : "wifi-btn disconnected")}
      tooltipText={getWifi.as((w) => w.connected ? `${w.ssid} (${w.signal}%)` : "WiFi disconnected")}
      onActivate={() => scanNetworks()}
    >
      <label label={getWifi.as((w) => wifiIcon(w))} />
      <popover>
        <box orientation={Gtk.Orientation.VERTICAL} class="wifi-popup" widthRequest={280}>
          <box class="wifi-header" spacing={8}>
            <label class="wifi-title" label="Wi-Fi Networks" hexpand={true} xalign={0} />
            <button
              class="wifi-refresh"
              onClicked={() => scanNetworks()}
              tooltipText="Refresh"
            >
              <label label={getWifi.as((w) => w.scanning ? "\uF110" : "\uF021")} />
            </button>
          </box>
          <PasswordEntry />
          <Gtk.ScrolledWindow
            vexpand={true}
            hscrollbarPolicy={Gtk.PolicyType.NEVER}
            maxContentHeight={300}
            propagateNaturalHeight={true}
          >
            <box orientation={Gtk.Orientation.VERTICAL} class="wifi-list" spacing={2}>
              {getWifi.as((w) =>
                w.networks.length > 0
                  ? w.networks.map((net) => <NetworkItem net={net} />)
                  : [<label class="wifi-empty" label={w.scanning ? "Scanning..." : "No networks found"} />]
              )}
            </box>
          </Gtk.ScrolledWindow>
        </box>
      </popover>
    </menubutton>
  )
}
