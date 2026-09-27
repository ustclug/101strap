#!/bin/sh
# Run an ARM64 command using native static BusyBox inside the guest chroot.
# This registration belongs only to the disposable appliance kernel.
set -eu
helper=/tmp/101strap/busybox
"$helper" mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
# Let guestfs clean up its /proc bind without leaving a nested mount behind.
trap '"$helper" umount /proc/sys/fs/binfmt_misc' EXIT
# Match little-endian AArch64 ELF executables and shared objects. F keeps the
# interpreter open while the guest command and its children run.
magic='\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\xb7\x00'
mask='\xff\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff'
printf ':101strap-aarch64:M::%s:%s:/tmp/101strap/qemu-aarch64:F\n' "$magic" "$mask" \
    > /proc/sys/fs/binfmt_misc/register
# Keep the registration mounted until the command and its children finish.
"$@"
