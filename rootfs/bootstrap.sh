#!/bin/bash
# Sourced only by rootfs/run-stage.sh.
# shellcheck disable=SC2034,SC2154
# Prepare runtime mounts before any guest package scripts run, on both arches.
debootstrap --arch="$ARCH" --foreign "$SUITE" "$ROOT" "$UBUNTU_MIRROR"
mount_guest
# Package installation must not start guest daemons against the host devices.
cat > "$ROOT/usr/sbin/policy-rc.d" <<'EOF'
#!/bin/sh
exit 101
EOF
chmod +x "$ROOT/usr/sbin/policy-rc.d"
chdo /debootstrap/debootstrap --second-stage

rm -f "$ROOT/etc/apt/sources.list"
write_ubuntu_sources "$UBUNTU_MIRROR" "$UBUNTU_SECURITY_MIRROR" > "$ROOT/etc/apt/sources.list.d/ubuntu.sources"
chdo apt update
chdo sh -c 'dpkg --get-selections | cut -f1 | xargs apt-mark auto'
