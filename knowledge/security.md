---
l0: "Security features: firewall (ufw), Bluetooth hardening, network hardening (sysctl), security agent, face authentication (howdy), touchscreen support"
l1_sections: ["Firewall", "Bluetooth Security", "Network Hardening", "Security Agent", "Face Authentication (Howdy)", "Touchscreen Support"]
tags: [firewall, ufw, bluetooth, network, sysctl, dns, security-agent, scan, face-auth, howdy, ir-camera, biometric, touchscreen, squeekboard, hyprgrass, pam, security, gesture, hardening, encryption]
---

# Costa OS Security

## Firewall

Costa OS ships with **ufw** (Uncomplicated Firewall) configured by default.

### Default Rules
- **Deny all incoming** — unsolicited inbound connections blocked
- **Allow all outgoing** — unrestricted outbound access
- Pre-allowed: mDNS (5353/udp), KDE Connect (1714-1764), Ollama local (11434 from localhost/Docker), Firecrawl local (3002 from localhost)
- SSH is NOT allowed by default — this is a desktop, not a server

### Commands
```bash
# Check status
sudo ufw status verbose

# Allow a specific port
sudo ufw allow 22/tcp comment "SSH"

# Deny a port
sudo ufw deny 8080

# Delete a rule
sudo ufw delete allow 22/tcp

# Reset to Costa defaults
sudo bash /usr/share/costa-os/configs/ufw/costa-defaults.sh

# Temporarily disable
sudo ufw disable

# Re-enable
sudo ufw enable
```

### Notes
- Docker manages its own iptables rules and can bypass ufw for published ports
- If you run Docker services accepting inbound connections, manage those via Docker's own network config
- To allow SSH: `sudo ufw allow ssh`

## Bluetooth Security

Bluetooth is hardened via `/etc/bluetooth/main.conf`:

- **Discoverable timeout**: 120 seconds — device auto-stops being visible
- **Pairable timeout**: 120 seconds — auto-stops accepting new pairings
- **LE encryption**: 128-bit minimum key size enforced
- **Auto-enable**: trusted devices reconnect on boot (desktop UX)

### Verify Settings
```bash
# Check bluetooth config
cat /etc/bluetooth/main.conf

# Check adapter state
bluetoothctl show
```

### Notes
- Some older Bluetooth devices may not support 128-bit keys — if pairing fails, check `/etc/bluetooth/main.conf` and lower `MinEncKeySize`
- Trusted (previously paired) devices reconnect automatically — this is intentional for headphones/speakers

## Network Hardening

System kernel parameters hardened via `/etc/sysctl.d/99-costa-hardening.conf`:

| Setting | Purpose |
|---------|---------|
| IP forwarding disabled | Not a router (Docker overrides per-bridge) |
| ICMP redirects blocked | Prevent MITM routing attacks |
| SYN cookies enabled | SYN flood protection |
| Source routing blocked | Prevent spoofed packets |
| Martian packet logging | Log packets with impossible source addresses |
| `kptr_restrict = 2` | Hide kernel memory addresses |
| `dmesg_restrict = 1` | Restrict kernel log to root |

### Verify
```bash
# Check a specific setting
sysctl net.ipv4.tcp_syncookies

# View all custom settings
sysctl --system 2>&1 | grep costa
```

### DNS
DNS is not encrypted by default (standard NetworkManager behavior). To enable DNS-over-TLS:
```bash
# Edit resolved.conf
sudo nano /etc/systemd/resolved.conf
# Set: DNS=1.1.1.1#cloudflare-dns.com
# Set: DNSOverTLS=yes

# Switch NetworkManager to use resolved
sudo nano /etc/NetworkManager/conf.d/dns.conf
# Set: [main]
#      dns=systemd-resolved

# Restart services
sudo systemctl enable --now systemd-resolved
sudo systemctl restart NetworkManager
```

## Security Agent

The security agent scans for vulnerabilities and reports findings.

### Usage
```bash
# Quick daily scan
costa-agents run security "efficient scan"

# Comprehensive scan
costa-agents run security "full scan"
```

### Scheduled Scans
- **Efficient**: daily at 3am — failed logins, open ports, outdated packages, firewall status
- **Full**: weekly Sunday 2:30am — all above plus setuid audit, systemd hardening scores, kernel params, BT security, package integrity

### What It Checks
**Efficient**: failed logins, listening ports, outdated packages, permission anomalies, firewall status, failed services
**Full**: all efficient checks plus setuid/setgid binaries, Bluetooth config, firewall rules, world-readable secrets, systemd unit security scores, sysctl verification, DNS servers, SSH key permissions, package integrity

The agent is read-only — it reports issues and suggests fixes but never modifies the system.

## Face Authentication (Howdy)

Costa OS supports Windows Hello-style face unlock using **Howdy** — a Linux face recognition system that works through PAM (Pluggable Authentication Modules).

### Requirements
- IR camera (infrared camera, commonly found in laptops with Windows Hello support)
- Detected automatically during first-boot via `v4l2-ctl`
- Password always works as fallback — face auth is "sufficient", not "required"

### How It Works
- Howdy captures your face via the IR camera and compares against enrolled face models
- PAM is configured with `auth sufficient` — if face matches, you're authenticated instantly
- If face doesn't match (wrong angle, glasses, darkness), password prompt appears normally
- Three PAM targets: `greetd` (login), `sudo` (privilege escalation), `hyprlock` (screen unlock)

### Commands
```bash
# Enroll a new face (required after install)
sudo howdy add

# Test face recognition (camera preview + match attempt)
sudo howdy test

# List enrolled face models
sudo howdy list

# Remove a face model
sudo howdy remove <id>

# Edit howdy configuration
sudo howdy config
```

### Configuration
- Howdy config: `/lib/security/howdy/config.ini`
- Key setting: `device_path` — auto-set to detected IR camera during first-boot
- Detection certainty: `certainty` (default 3.5, lower = stricter matching)
- PAM entries: `/etc/pam.d/greetd`, `/etc/pam.d/sudo`, `/etc/pam.d/hyprlock`

### Troubleshooting
- **"No face model" error**: Run `sudo howdy add` to enroll your face
- **Camera not found**: Check `v4l2-ctl --list-devices` for your IR camera path
- **False positives**: Lower `certainty` value in howdy config (e.g., 3.0)
- **Slow recognition**: IR camera may need better lighting; try enrolling multiple angles
- **Disable face auth**: Remove the howdy line from `/etc/pam.d/sudo` (or other PAM files)
- **Re-enable**: Add `auth sufficient pam_python.so /lib/security/howdy/pam.py` as first auth line

### Important Notes
- Howdy is **convenience, not security-grade** — it can be fooled by photos in some conditions
- The IR camera helps significantly vs regular webcams (harder to spoof with printed photos)
- Never rely solely on face auth for sensitive operations — password remains the security baseline
- Howdy is an AUR package — installed via `yay`, not in the base ISO

## Touchscreen Support

### Components
- **libinput** — kernel-level touch input (built into Hyprland)
- **squeekboard** — on-screen keyboard (auto-starts if touchscreen detected)
- **hyprgrass** — Hyprland plugin for multi-touch gestures (AUR)

### Touch Gestures (hyprgrass)
- 3-finger swipe up → app launcher (rofi)
- 3-finger swipe down → close window
- 3-finger swipe left/right → switch workspace
- 4-finger swipe up → fullscreen
- 4-finger swipe down → toggle floating
- Long press (2 fingers) → move window

### Configuration
- Touch config: `~/.config/hypr/touch.conf` (auto-generated by first-boot)
- Sourced from `hyprland.conf` automatically
- Squeekboard window rule: floats, pins to bottom of screen

### Troubleshooting
- **Squeekboard not appearing**: Check `pgrep squeekboard`; restart with `squeekboard &disown`
- **Gestures not working**: Verify hyprgrass plugin is loaded: `hyprctl plugin list`
- **Touch not responding**: Check `libinput list-devices` for your touchscreen
- **Wrong touch mapping on rotated display**: Set `transform` in `touch.conf` to match your monitor rotation
