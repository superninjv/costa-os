---
l0: "Arch Linux administration: pacman/yay package management, systemd services, system logs"
l1_sections: ["Package Management", "Systemd Services", "Common Tasks"]
tags: [pacman, yay, aur, package, install, update, systemd, service, journal, orphan, cache, downgrade]
---
# Arch Linux Administration

## Package Management
- Install: `pacman -S pkg` (official), `yay -S pkg` (AUR)
- Remove: `pacman -Rns pkg` (with deps + config)
- Search: `pacman -Ss keyword`, `yay -Ss keyword`
- Info: `pacman -Qi pkg` (installed), `pacman -Si pkg` (remote)
- List installed: `pacman -Qq`, filter: `pacman -Qq | grep keyword`
- Update: `yay -Syu` (system + AUR), `pacman -Syu` (official only)
- List orphans: `pacman -Qtdq`, remove: `pacman -Rns $(pacman -Qtdq)`
- Check which package owns a file: `pacman -Qo /path/to/file`
- List files in package: `pacman -Ql pkg`
- Downgrade: `pacman -U /var/cache/pacman/pkg/package-version.pkg.tar.zst`

## Systemd Services
- Status: `systemctl status svc`, user: `systemctl --user status svc`
- Start/stop/restart: `systemctl start|stop|restart svc`
- Enable/disable boot: `systemctl enable|disable svc`
- List running: `systemctl list-units --state=running`
- List failed: `systemctl --failed`
- View logs: `journalctl -u svc`, follow: `journalctl -fu svc`
- User services live in `~/.config/systemd/user/`

## Common Tasks
- System logs: `journalctl -b` (this boot), `-p err` (errors only)
- Kernel messages: `dmesg --level=err,warn`
- Disk usage: `df -h`, per-directory: `du -sh /path/*`
- Find large files: `find / -type f -size +500M 2>/dev/null`
- Network: `ip addr`, `ss -tlnp` (listening ports)
- Process by resource: `ps aux --sort=-%mem | head -20`
- Kill by name: `pkill -f processname`
- Clear pacman cache: `paccache -rk2` (keep last 2 versions)
