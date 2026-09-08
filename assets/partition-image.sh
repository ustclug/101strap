#!/bin/bash
# Write the image's GPT layout to an attached disk or a sparse test file.
set -euo pipefail

disk=${1:?disk path required}
disk_size_mib=${2:?disk size in MiB required}
esp_size_mib=${3:?EFI partition size in MiB required}

# Leave 1 MiB at either end for GPT and align both partitions to MiB boundaries.
root_start_mib=$((1 + esp_size_mib))
root_end_mib=$((disk_size_mib - 1))
parted --script -a optimal "$disk" mklabel gpt \
    mkpart '"EFI System"' fat32 1MiB "${root_start_mib}MiB" set 1 esp on \
    mkpart '"Linux system"' ext4 "${root_start_mib}MiB" "${root_end_mib}MiB"
