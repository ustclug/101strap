#!/bin/bash
# Package a VMDK as a VMware OVA using open-vmdk.
set -euo pipefail

source_disk=${1:?source VMDK required}
output=${2:?output OVA required}
if [[ -e "$output" || -L "$output" ]]; then
    echo "Refusing to overwrite $output" >&2
    exit 1
fi
source_disk=$(realpath -- "$source_disk")
output=$(realpath -m -- "$output")
# Reject invalid input before open-vmdk attempts to interpret it as a raw disk.
qemu-img info -f vmdk "$source_disk" >/dev/null
asset_directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
vm_name=$(basename -- "$output" .ova)

# The standalone VMDK remains suitable for manual import. OVA needs its own
# stream-optimized copy, which is removed after packaging (including on failure).
work_directory=$(mktemp -d "$(dirname -- "$output")/.vmware-export.XXXXXX")
trap 'rm -rf -- "$work_directory"' EXIT
vmdk-convert "$source_disk" "$work_directory/root.vmdk"
cd -- "$work_directory"
ova-compose -i "$asset_directory/vmware.yaml" -o "$vm_name.ova" \
    --param "name=$vm_name" --param "disk=root.vmdk"
mv -- "$vm_name.ova" "$output"
