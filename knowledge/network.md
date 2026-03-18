---
l0: "Network management: WiFi, ethernet, VPN, DNS, SSH, firewall, diagnostics"
l1_sections: ["WiFi", "Wired/Ethernet", "IP & Interface Info", "DNS", "Firewall (if installed)", "VPN", "Diagnostics", "Hostname", "SSH"]
tags: [wifi, ethernet, vpn, wireguard, dns, ssh, firewall, nmcli, ip-address, speed-test, hostname]
---

# Network Management

## WiFi
- List available: `nmcli device wifi list`
- Connect: `nmcli device wifi connect "SSID" password "PASSWORD"`
- Disconnect: `nmcli connection down "SSID"`
- Saved connections: `nmcli connection show`
- Delete saved: `nmcli connection delete "SSID"`
- WiFi on/off: `nmcli radio wifi on|off`
- Interactive: `nmtui`

## Wired/Ethernet
- Status: `nmcli device status`
- Enable: `nmcli device connect eth0`
- DHCP renew: `sudo nmcli connection down "Wired" && sudo nmcli connection up "Wired"`

## IP & Interface Info
- IP addresses: `ip addr` or `ip -br addr`
- Default gateway: `ip route | grep default`
- DNS servers: `resolvectl status` or `cat /etc/resolv.conf`
- Public IP: `curl -s ifconfig.me`
- All interfaces: `nmcli device status`

## DNS
- Test resolution: `dig google.com` or `dog google.com` (if installed)
- Set custom DNS: `nmcli connection modify "SSID" ipv4.dns "1.1.1.1 8.8.8.8"`
- Apply changes: `nmcli connection up "SSID"`

## Firewall (if installed)
- Status: `sudo ufw status` or `sudo firewall-cmd --state`
- Allow port: `sudo ufw allow 8080`
- Deny port: `sudo ufw deny 8080`

## VPN
- WireGuard: `sudo wg-quick up wg0`, `sudo wg-quick down wg0`
- OpenVPN: `sudo openvpn --config file.ovpn`
- NetworkManager VPN: `nmcli connection up VPN_NAME`
- Import WireGuard config: `nmcli connection import type wireguard file wg0.conf`

## Diagnostics
- Ping: `ping -c4 archlinux.org`
- Traceroute: `traceroute archlinux.org`
- Port check: `ss -tlnp` (listening), `ss -tnp` (all connections)
- Bandwidth monitor: `bandwhich` (requires sudo)
- Speed test: `curl -s https://raw.githubusercontent.com/sivel/speedtest-cli/master/speedtest.py | python3`

## Hostname
- Current: `hostnamectl`
- Change: `sudo hostnamectl set-hostname newhostname`

## SSH
- Connect: `ssh user@host`
- With key: `ssh -i ~/.ssh/id_ed25519 user@host`
- Copy key to server: `ssh-copy-id user@host`
- Generate key: `ssh-keygen -t ed25519`
- SSH config: `~/.ssh/config`
