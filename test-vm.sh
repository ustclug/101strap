#!/bin/bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# shellcheck source=config.sh
source ./config.sh
DISK="$PWD/build101/$ARCH/root.qcow2"
test -r "$DISK"

if [[ "$ARCH" == arm64 ]]; then
    emulator=qemu-system-aarch64
    machine=virt
    cpu=max
    native_host=aarch64
    firmware_candidates=(
        /usr/share/edk2/aarch64/QEMU_EFI.fd
        /usr/share/AAVMF/AAVMF_CODE.fd
    )
    vars_candidates=(
        /usr/share/edk2/aarch64/QEMU_VARS.fd
        /usr/share/AAVMF/AAVMF_VARS.fd
    )
    graphics=(-device virtio-gpu-pci)
else
    emulator=qemu-system-x86_64
    machine=q35
    cpu=max
    native_host=x86_64
    firmware_candidates=(
        /usr/share/edk2/x64/OVMF_CODE.4m.fd
        /usr/share/OVMF/OVMF_CODE_4M.fd
    )
    vars_candidates=(
        /usr/share/edk2/x64/OVMF_VARS.4m.fd
        /usr/share/OVMF/OVMF_VARS_4M.fd
    )
    graphics=(-vga vmware)
fi
command -v "$emulator" >/dev/null
if [[ -z "${FIRMWARE_CODE:-}" && -z "${FIRMWARE_VARS:-}" ]]; then
    for i in "${!firmware_candidates[@]}"; do
        if [[ -r "${firmware_candidates[$i]}" && -r "${vars_candidates[$i]}" ]]; then
            FIRMWARE_CODE=${firmware_candidates[$i]}
            FIRMWARE_VARS=${vars_candidates[$i]}
            break
        fi
    done
fi
if [[ ! -r "${FIRMWARE_CODE:-}" || ! -r "${FIRMWARE_VARS:-}" ]]; then
    echo "Set FIRMWARE_CODE and FIRMWARE_VARS to a matching pair of UEFI firmware files." >&2
    exit 1
fi
accel=tcg
if [[ "$(uname -m)" == "$native_host" && -r /dev/kvm && -w /dev/kvm ]]; then
    accel=kvm
    cpu=host
fi

# -snapshot preserves the built disk; firmware variables are disposable too.
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/101strap-vm.XXXXXX")
trap 'rm -f -- "$test_dir/vars.fd"; rmdir -- "$test_dir"' EXIT
cp -- "$FIRMWARE_VARS" "$test_dir/vars.fd"
echo "Testing $ARCH with $accel; disk changes will be discarded on exit."
"$emulator" -machine "$machine,accel=$accel" -cpu "$cpu" -smp 2 -m 4096 \
    -drive "if=pflash,format=raw,unit=0,readonly=on,file=$FIRMWARE_CODE" \
    -drive "if=pflash,format=raw,unit=1,file=$test_dir/vars.fd" \
    -drive "if=virtio,format=qcow2,file=$DISK" -snapshot \
    -netdev user,id=net101 -device virtio-net-pci,netdev=net101 \
    "${graphics[@]}" -device qemu-xhci -device usb-kbd -device usb-tablet \
    -display "${QEMU_DISPLAY:-gtk}" -serial mon:stdio
