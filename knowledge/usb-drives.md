---
l0: "USB and external storage: detecting, mounting, ejecting, formatting drives"
l1_sections: ["CRITICAL: Do NOT format or wipe drives unless the user explicitly asks", "Detect Drives", "Mount", "Eject / Unmount", "Format (ONLY if user explicitly asks)", "Flash ISO to USB", "Check Filesystem", "Common Paths"]
tags: [usb, mount, unmount, eject, external-drive, format, fat32, ntfs, ext4, lsblk, udisks]
---

# USB Drives & External Storage

## CRITICAL: Do NOT format or wipe drives unless the user explicitly asks
"Mount", "open", "access" a drive means MOUNT it, not format it.

## Detect Drives
- List all drives: `lsblk`
- List with details: `lsblk -f` (shows filesystem, label, UUID, mount point)
- USB devices: `lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,MODEL`
- Watch for new drives: `dmesg -w` (shows kernel messages as devices are plugged in)

## Mount
- Auto-mount (recommended): most USB drives auto-mount via gvfs/udisks2
- Check if mounted: `lsblk` (look for MOUNTPOINT column)
- Mount manually: `sudo mount /dev/sdX1 /mnt`
- Mount as user (udisks2): `udisksctl mount -b /dev/sdX1`
- Mounted drives appear in Thunar sidebar automatically
- Open in file manager: `thunar /run/media/$USER/LABEL`

## Eject / Unmount
- Safe eject: `udisksctl unmount -b /dev/sdX1 && udisksctl power-off -b /dev/sdX`
- Unmount only: `sudo umount /dev/sdX1` or `udisksctl unmount -b /dev/sdX1`
- If busy: `sudo umount -l /dev/sdX1` (lazy unmount, completes when not in use)
- Find what's using it: `sudo lsof /run/media/$USER/LABEL`

## Format (ONLY if user explicitly asks)
- Format as ext4: `sudo mkfs.ext4 /dev/sdX1`
- Format as FAT32 (USB compatible): `sudo mkfs.fat -F32 /dev/sdX1`
- Format as NTFS (Windows compatible): `sudo mkfs.ntfs /dev/sdX1`
- Partition first: `sudo parted /dev/sdX mklabel gpt` then `sudo parted /dev/sdX mkpart primary ext4 0% 100%`

## Flash ISO to USB
- `sudo dd if=image.iso of=/dev/sdX bs=4M status=progress conv=fsync`
- WARNING: this erases everything on the drive. Use the whole device (/dev/sdX), not a partition (/dev/sdX1)

## Check Filesystem
- `sudo fsck /dev/sdX1` (unmount first!)
- `sudo smartctl -a /dev/sdX` (SMART health, needs smartmontools)

## Common Paths
- Auto-mounted USB: `/run/media/$USER/DRIVELABEL`
- Manual mount point: `/mnt` or create your own with `mkdir`
