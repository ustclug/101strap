#!/bin/bash
# shellcheck source=rootfs/config.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/rootfs/config.sh"
# shellcheck disable=SC2034
DISK_SIZE_MIB=16384
# shellcheck disable=SC2034
ESP_SIZE_MIB=256
if [[ "$ARCH" == amd64 ]]; then
    FORMAT=${FORMAT:-all}
else
    FORMAT=${FORMAT:-qcow2}
fi
case "$FORMAT" in
    all|qcow2) ;;
    *) echo "Unsupported FORMAT: $FORMAT (expected all or qcow2)" >&2; exit 1 ;;
esac
if [[ "$ARCH" == arm64 && "$FORMAT" != qcow2 ]]; then
    echo "arm64 currently supports FORMAT=qcow2 only" >&2
    exit 1
fi

CACHE_EPOCH=${CACHE_EPOCH:-0}
if [[ ! "$CACHE_EPOCH" =~ ^[a-zA-Z0-9._-]{1,64}$ ]]; then
    echo 'CACHE_EPOCH must be 1-64 letters, digits, dots, underscores or hyphens' >&2
    exit 1
fi
