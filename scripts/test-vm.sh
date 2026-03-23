#!/bin/bash
# Launch Costa OS ISO in QEMU for testing
# Usage: ./scripts/test-vm.sh [path-to-iso]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUT_DIR="$PROJECT_DIR/out"
VM_DIR="$PROJECT_DIR/vm"

# Find ISO
if [ -n "$1" ]; then
    ISO="$1"
else
    ISO=$(ls -t "$OUT_DIR"/costa-os-*.iso 2>/dev/null | head -1)
fi

if [ -z "$ISO" ] || [ ! -f "$ISO" ]; then
    echo "No ISO found. Build one first: sudo ./scripts/build-iso.sh"
    exit 1
fi

echo "→ Booting ISO: $(basename "$ISO")"

# Create VM disk if needed
mkdir -p "$VM_DIR"
DISK="$VM_DIR/costa-test.qcow2"
if [ ! -f "$DISK" ]; then
    echo "→ Creating 40GB test disk..."
    qemu-img create -f qcow2 "$DISK" 40G
fi

# Get OVMF firmware path
OVMF="/usr/share/edk2/x64/OVMF.4m.fd"
if [ ! -f "$OVMF" ]; then
    OVMF="/usr/share/edk2-ovmf/x64/OVMF.4m.fd"
fi
if [ ! -f "$OVMF" ]; then
    echo "OVMF not found. Install: sudo pacman -S edk2-ovmf"
    exit 1
fi

# Copy OVMF vars (writable) for this VM
OVMF_VARS="$VM_DIR/OVMF_VARS.fd"
if [ ! -f "$OVMF_VARS" ]; then
    OVMF_VARS_SRC="/usr/share/edk2/x64/OVMF_VARS.4m.fd"
    [ ! -f "$OVMF_VARS_SRC" ] && OVMF_VARS_SRC="/usr/share/edk2-ovmf/x64/OVMF_VARS.4m.fd"
    cp "$OVMF_VARS_SRC" "$OVMF_VARS"
fi

echo "→ Launching QEMU (8GB RAM, 4 cores, EFI)..."
echo "   Press Ctrl+Alt+G to release mouse"
echo ""

SERIAL_LOG="$VM_DIR/serial.log"

qemu-system-x86_64 \
    -enable-kvm \
    -m 8G \
    -smp 4 \
    -cpu host \
    -drive if=pflash,format=raw,readonly=on,file="$OVMF" \
    -drive if=pflash,format=raw,file="$OVMF_VARS" \
    -drive file="$DISK",format=qcow2,if=virtio \
    -cdrom "$ISO" \
    -boot d \
    -vga qxl \
    -display gtk \
    -device virtio-net-pci,netdev=net0 \
    -netdev user,id=net0 \
    -device ich9-intel-hda \
    -device hda-duplex \
    -usb \
    -device usb-tablet \
    -serial file:"$SERIAL_LOG" \
    -monitor unix:"$VM_DIR/qemu-monitor.sock",server,nowait \
    "$@"
