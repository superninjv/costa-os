---
l0: "Bluetooth management: pairing, connecting, audio devices, game controllers, troubleshooting"
l1_sections: ["Quick Commands", "Common Workflows", "Service", "Troubleshooting"]
tags: [bluetooth, pair, connect, headphone, earbuds, controller, speaker, bluetoothctl, audio-switch]
---

# Bluetooth

## Quick Commands
- Turn on: `bluetoothctl power on`
- Turn off: `bluetoothctl power off`
- Scan for devices: `bluetoothctl scan on` (Ctrl+C to stop)
- List found devices: `bluetoothctl devices`
- Pair: `bluetoothctl pair XX:XX:XX:XX:XX:XX`
- Connect: `bluetoothctl connect XX:XX:XX:XX:XX:XX`
- Disconnect: `bluetoothctl disconnect XX:XX:XX:XX:XX:XX`
- Remove/forget: `bluetoothctl remove XX:XX:XX:XX:XX:XX`
- Trust (auto-connect): `bluetoothctl trust XX:XX:XX:XX:XX:XX`
- Show connected: `bluetoothctl info`
- List paired: `bluetoothctl paired-devices`

## Common Workflows

### Pair Bluetooth headphones/speaker
```
bluetoothctl power on
bluetoothctl scan on
# Wait for device to appear, note the MAC address
bluetoothctl pair XX:XX:XX:XX:XX:XX
bluetoothctl trust XX:XX:XX:XX:XX:XX
bluetoothctl connect XX:XX:XX:XX:XX:XX
```

### Switch audio to Bluetooth device after connecting
```
# List sinks to find the Bluetooth device
pactl list sinks short
# Set it as default
pactl set-default-sink bluez_output.XX_XX_XX_XX_XX_XX.1
```

### Pair game controller
Same as headphones. Most controllers work automatically once paired.
For PS5 DualSense: hold Share + PS button until light flashes fast, then pair.
For Xbox: hold sync button until logo flashes, then pair.

## Service
- `systemctl status bluetooth`
- `systemctl start bluetooth`
- `systemctl enable bluetooth` (auto-start on boot)

## Troubleshooting
- Not finding devices: `bluetoothctl power off && bluetoothctl power on && bluetoothctl scan on`
- Device pairs but no audio: check `pactl list sinks short` and switch default sink
- Stuttering audio: try `bluetoothctl disconnect` then reconnect
- Device won't pair: `bluetoothctl remove XX:XX:XX:XX:XX:XX` then try again
- Check adapter exists: `bluetoothctl show`
