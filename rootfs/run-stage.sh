#!/bin/bash
# Every RUN must finish with no guest mounts left in its container layer.
# Variables and helpers are consumed by the selected stage script.
# shellcheck disable=SC2034
set -euo pipefail
# shellcheck source=rootfs/config.sh
source /recipe/config.sh
ROOT=/rootfs
HOST_ARCH=$(dpkg --print-architecture)
IMAGE_USER=ustc
PASSWORD=ustc
stage=${1:?stage required}
case "$stage" in bootstrap|desktop|applications|kernel|configured) ;; *) exit 2 ;; esac
[[ $EUID == 0 ]] || exit 1

chdo() { chroot "$ROOT" "$@"; }
inspkg() { DEBIAN_FRONTEND=noninteractive chroot "$ROOT" apt-get install --no-install-recommends --yes "$@"; }
unmount_guest() {
    local path failed=0
    for path in dev sys proc; do
        if mountpoint -q "$ROOT/$path"; then
            umount -R "$ROOT/$path" || failed=1
        fi
    done
    return "$failed"
}
cleanup() {
    local status=$?
    trap - EXIT
    unmount_guest || status=1
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mount_guest() {
    mkdir -p "$ROOT"/{dev,proc,sys,run}
    mount -t proc proc "$ROOT/proc"
    mount --bind /sys "$ROOT/sys"
    mount -o remount,bind,ro "$ROOT/sys"
    mount -t tmpfs -o mode=755 tmpfs "$ROOT/dev"
    # Bind only basic character devices, never the host disk devices.
    for device in null zero full random urandom tty; do
        touch "$ROOT/dev/$device"
        mount --bind "/dev/$device" "$ROOT/dev/$device"
    done
    mkdir -p "$ROOT/dev/pts" "$ROOT/dev/shm"
    mount -t devpts -o newinstance,ptmxmode=0666,mode=0620 devpts "$ROOT/dev/pts"
    ln -s pts/ptmx "$ROOT/dev/ptmx"
    ln -s /proc/self/fd "$ROOT/dev/fd"
    ln -s /proc/self/fd/0 "$ROOT/dev/stdin"
    ln -s /proc/self/fd/1 "$ROOT/dev/stdout"
    ln -s /proc/self/fd/2 "$ROOT/dev/stderr"
    # Refresh build-only DNS, including after restoring a layer on another host.
    rm -f "$ROOT/etc/resolv.conf"
    cp -L /etc/resolv.conf "$ROOT/etc/resolv.conf"
}
if [[ "$stage" != bootstrap ]]; then
    mount_guest
fi
# shellcheck disable=SC1090
source "/recipe/$stage.sh"
unmount_guest
# Do not persist the builder's DNS or transient runtime data in a guest layer.
rm -f "$ROOT/etc/resolv.conf"
ln -s /run/systemd/resolve/stub-resolv.conf "$ROOT/etc/resolv.conf"
find "$ROOT/run" "$ROOT/tmp" -mindepth 1 -delete
mkdir -p /rootfs-build
printf '%s\n' "$ARCH" > /rootfs-build/architecture
printf '%s\n' "$BUILD_MIRROR_MODE" > /rootfs-build/mirror-mode
printf '%s\n' "${CACHE_EPOCH:?}" > /rootfs-build/cache-epoch
printf '%s\n' "$stage" > /rootfs-build/stage
date -u +%Y-%m-%dT%H:%M:%SZ > /rootfs-build/built-at
