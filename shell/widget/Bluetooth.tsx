import { Gtk } from "ags/gtk4"
import { execAsync } from "ags/process"
import GLib from "gi://GLib"
import { lockBar, unlockBar } from "../lib/state"

interface BtDevice {
  mac: string
  name: string
  connected: boolean
  paired: boolean
}

let powered = false
let connectedName = ""
let devices: BtDevice[] = []
let scanning = false
let connectingMac = ""
let operationInFlight = false

function isValidMac(mac: string): boolean {
  return /^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$/.test(mac)
}

// Listeners to notify on state change
const listeners: (() => void)[] = []
function notify() { for (const fn of listeners) fn() }

function pollBt() {
  execAsync("bash -c \"bluetoothctl show | grep -q 'Powered: yes' && echo powered || echo off\"")
    .then((out) => {
      powered = out.trim() === "powered"
      if (powered) {
        execAsync("bash -c \"bluetoothctl devices Connected | head -1 | cut -d' ' -f3-\"")
          .then((dev) => { connectedName = dev.trim(); notify() })
          .catch(() => { connectedName = ""; notify() })
      } else {
        connectedName = ""
        notify()
      }
    })
    .catch(() => { powered = false; connectedName = ""; notify() })
}

let scanTimers: number[] = []

function scanDevices() {
  if (!powered || scanning) return
  scanning = true
  notify()

  // Clear any stale timers
  for (const id of scanTimers) GLib.source_remove(id)
  scanTimers = []

  execAsync("bluetoothctl scan on").catch(() => {})
  scanTimers.push(GLib.timeout_add(GLib.PRIORITY_DEFAULT, 4000, () => {
    execAsync("bluetoothctl scan off").catch(() => {})
    return GLib.SOURCE_REMOVE
  }))

  refreshDevices()
  scanTimers.push(GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => { refreshDevices(); return GLib.SOURCE_REMOVE }))
  scanTimers.push(GLib.timeout_add(GLib.PRIORITY_DEFAULT, 4500, () => {
    refreshDevices()
    scanning = false
    scanTimers = []
    notify()
    return GLib.SOURCE_REMOVE
  }))
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
            const name = parts.slice(2).join(" ")
            if (!mac || seen.has(mac)) continue
            if (name === mac || name.startsWith("00:") || name.startsWith("FF:")) continue
            seen.add(mac)
            devs.push({ mac, name, connected: connMacs.has(mac), paired: pairMacs.has(mac) })
          }

          devs.sort((a, b) => {
            if (a.connected && !b.connected) return -1
            if (!a.connected && b.connected) return 1
            if (a.paired && !b.paired) return -1
            if (!a.paired && b.paired) return 1
            return a.name.localeCompare(b.name)
          })

          devices = devs
          notify()
        })
        .catch(() => {})
    })
    .catch(() => {})
}

function handleDevice(mac: string, isPaired: boolean, isConnected: boolean) {
  if (operationInFlight || !isValidMac(mac)) return
  operationInFlight = true
  connectingMac = mac
  notify()
  let cmd: string
  if (isConnected) cmd = `bluetoothctl disconnect '${mac}'`
  else if (isPaired) cmd = `bluetoothctl connect '${mac}'`
  else cmd = `bash -c "bluetoothctl pair '${mac}' && bluetoothctl trust '${mac}' && bluetoothctl connect '${mac}'"`

  execAsync(cmd)
    .then(() => {
      GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => { pollBt(); refreshDevices(); return GLib.SOURCE_REMOVE })
    })
    .catch(() => {})
    .finally(() => { operationInFlight = false; connectingMac = ""; notify() })
}

function togglePower() {
  execAsync(`bluetoothctl ${powered ? "power off" : "power on"}`).catch(() => {})
  GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => { pollBt(); return GLib.SOURCE_REMOVE })
}

pollBt()
refreshDevices()
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 5000, () => { pollBt(); return GLib.SOURCE_CONTINUE })

function clearChildren(box: Gtk.Box) {
  let c = box.get_first_child()
  while (c) { const n = c.get_next_sibling(); box.remove(c); c = n }
}

export default function Bluetooth() {
  const deviceList = new Gtk.Box({ orientation: Gtk.Orientation.VERTICAL, cssClasses: ["bt-list"], spacing: 2 })
  const btnLabel = new Gtk.Label({ label: "\uF294" })

  function render() {
    // Update device list
    clearChildren(deviceList)

    if (!powered) {
      deviceList.append(new Gtk.Label({ cssClasses: ["bt-empty"], label: "Bluetooth is off" }))
      return
    }

    if (devices.length === 0) {
      deviceList.append(new Gtk.Label({
        cssClasses: ["bt-empty"],
        label: scanning ? "Scanning..." : "No devices found",
      }))
      return
    }

    for (const dev of devices) {
      const isConn = connectingMac === dev.mac
      const row = new Gtk.Button({
        cssClasses: dev.connected ? ["bt-dev-item", "connected"] : ["bt-dev-item"],
        sensitive: !isConn,
      })
      const box = new Gtk.Box({ spacing: 8 })
      box.append(new Gtk.Label({ cssClasses: ["bt-dev-icon"], label: dev.connected ? "\uF293" : "\uF294" }))
      box.append(new Gtk.Label({
        cssClasses: ["bt-dev-name"],
        label: isConn ? `${dev.name}...` : dev.name,
        hexpand: true,
        xalign: 0,
      }))
      if (dev.connected) box.append(new Gtk.Label({ cssClasses: ["bt-dev-check"], label: "\uF00C" }))
      else if (dev.paired) box.append(new Gtk.Label({ cssClasses: ["bt-dev-paired"], label: "paired" }))
      else box.append(new Gtk.Label({ cssClasses: ["bt-dev-paired"], label: "new" }))

      row.set_child(box)
      row.connect("clicked", () => handleDevice(dev.mac, dev.paired, dev.connected))
      deviceList.append(row)
    }
  }

  listeners.push(render)
  render()

  const scroll = new Gtk.ScrolledWindow({
    vexpand: true,
    hscrollbarPolicy: Gtk.PolicyType.NEVER,
    maxContentHeight: 250,
    propagateNaturalHeight: true,
  })
  scroll.set_child(deviceList)

  const popupBox = new Gtk.Box({ orientation: Gtk.Orientation.VERTICAL, cssClasses: ["bt-popup"], widthRequest: 260 })

  const header = new Gtk.Box({ cssClasses: ["bt-header"], spacing: 8 })
  header.append(new Gtk.Label({ cssClasses: ["bt-title"], label: "Bluetooth", hexpand: true, xalign: 0 }))

  const scanBtn = new Gtk.Button({ cssClasses: ["bt-scan"], tooltipText: "Scan" })
  scanBtn.set_child(new Gtk.Label({ label: "\uF002" }))
  scanBtn.connect("clicked", () => scanDevices())

  const powerBtn = new Gtk.Button({ cssClasses: ["bt-power"], tooltipText: "Toggle power" })
  powerBtn.set_child(new Gtk.Label({ label: "\uF011" }))
  powerBtn.connect("clicked", () => togglePower())

  header.append(scanBtn)
  header.append(powerBtn)
  popupBox.append(header)
  popupBox.append(scroll)

  const popover = new Gtk.Popover()
  popover.set_child(popupBox)
  popover.connect("notify::visible", () => {
    if (popover.visible) {
      lockBar()
      if (powered) { refreshDevices(); scanDevices() }
    } else {
      unlockBar()
    }
  })

  const menuBtn = new Gtk.MenuButton({
    cssClasses: ["bt-btn"],
    popover: popover,
    tooltipText: powered ? (connectedName || "Bluetooth on") : "Bluetooth off",
  })
  const menuLabel = new Gtk.Label({ label: powered ? "\uF293" : "\uF294" })
  menuBtn.set_child(menuLabel)

  listeners.push(() => {
    menuBtn.tooltipText = powered
      ? (connectedName ? `Connected: ${connectedName}` : "Bluetooth on (no device)")
      : "Bluetooth off"
    const cls = !powered ? "bt-btn off" : connectedName ? "bt-btn connected" : "bt-btn on"
    menuBtn.cssClasses = [cls]
    menuLabel.label = powered ? "\uF293" : "\uF294"
  })

  return menuBtn as Gtk.Widget
}
