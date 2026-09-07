#!/bin/bash
# Variables are consumed by the scripts sourcing this file.
# shellcheck disable=SC2034

# Shared by the host wrapper and the container entry points.
RELEASE=26.04
SUITE=resolute
DISK_SIZE_MIB=16384
ESP_SIZE_MIB=256
# Use one complete repository for Firefox and its architecture-independent l10n packages.
MOZILLA_MIRROR=https://packages.mozilla.org/apt
ARCH=${ARCH:-amd64}
case "$ARCH" in
    amd64)
        UBUNTU_MIRROR=https://mirrors.ustc.edu.cn/ubuntu
        GRUB_TARGET=x86_64-efi
        GRUB_PACKAGE=grub-efi-amd64
        FORMAT=${FORMAT:-all}
        ;;
    arm64)
        UBUNTU_MIRROR=https://mirrors.ustc.edu.cn/ubuntu-ports
        GRUB_TARGET=arm64-efi
        GRUB_PACKAGE=grub-efi-arm64
        FORMAT=${FORMAT:-qcow2}
        ;;
    *) echo "Unsupported ARCH: $ARCH (expected amd64 or arm64)" >&2; exit 1 ;;
esac
case "$FORMAT" in
    all|qcow2) ;;
    *) echo "Unsupported FORMAT: $FORMAT (expected all or qcow2)" >&2; exit 1 ;;
esac
if [[ "$ARCH" == arm64 && "$FORMAT" != qcow2 ]]; then
    echo "arm64 currently supports FORMAT=qcow2 only" >&2
    exit 1
fi
