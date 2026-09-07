#!/bin/bash
# Idempotent fallback for failed builds and cancellation. Never identify by name alone.
set -euo pipefail
: "${RUNNER_TEMP:?}"
logs="$RUNNER_TEMP/101strap"
mkdir -p "$logs"
exec >> "$logs/cleanup.log" 2>&1
date -u
timeout 10s df -h || true
timeout 10s sudo docker ps -a --no-trunc || true
timeout 10s sudo docker system df || true
[[ -s "$logs/container.cid" ]] || exit 0
cid=$(cat "$logs/container.cid")
[[ "$cid" =~ ^[0-9a-f]{64}$ ]] || exit 1
# A vanished --rm container has nothing left to stop. Do not touch any NBD then.
timeout 10s sudo docker inspect "$cid" > "$logs/container.json" || exit 0
pid=$(cat /sys/class/block/nbd0/pid 2>/dev/null || true)
owned=no
if [[ "$pid" =~ ^[0-9]+$ ]] &&
   sudo grep -Fq "$cid" "/proc/$pid/cgroup" &&
   sudo cat "/proc/$pid/cmdline" | tr '\0' '\n' | grep -Fxq /target/root.qcow2; then
    owned=yes
fi
timeout 10s sudo docker logs "$cid" > "$logs/container.log" 2>&1 || true
# SIGTERM may not reach the entrypoint's shell; Docker kills the container after 20s.
timeout 30s sudo docker stop --time 20 "$cid"
if [[ "$owned" == yes && "$(cat /sys/class/block/nbd0/pid 2>/dev/null || true)" == "$pid" ]]; then
    # Recheck ownership after stopping, in case a PID was recycled.
    sudo grep -Fq "$cid" "/proc/$pid/cgroup"
    timeout 15s sudo qemu-nbd --disconnect /dev/nbd0
fi
