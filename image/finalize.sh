#!/bin/bash
# Runs inside the guest chroot in the libguestfs appliance.
set -euxo pipefail
ARCH=${1:?guest architecture required}
# shellcheck source=rootfs/config.sh
source /tmp/101strap/config.sh

root_uuid=$(blkid -s UUID -o value /dev/sda2)
efi_uuid=$(blkid -s UUID -o value /dev/sda1)
printf 'UUID=%s\t/\text4\trw,relatime\t0\t1\nUUID=%s\t/boot/efi\tvfat\trw,relatime\t0\t1\n' \
    "$root_uuid" "$efi_uuid" > /etc/fstab

# Use the guest's GRUB 2, not guestfish's legacy GRUB 1 API.
update-initramfs -k all -c
grub-install --target="$GRUB_TARGET" --efi-directory=/boot/efi --removable --no-nvram
update-grub

# Guestfish --network supplies a temporary resolver while this command runs.
write_ubuntu_sources "$DELIVERY_UBUNTU_MIRROR" "$DELIVERY_UBUNTU_MIRROR" > /etc/apt/sources.list.d/ubuntu.sources
write_mozilla_sources "$DELIVERY_MOZILLA_MIRROR" > /etc/apt/sources.list.d/mozilla.list
flatpak remote-modify flathub --url=https://mirrors.ustc.edu.cn/flathub
apt-get -o APT::Update::Error-Mode=any update
apt-get clean
rm -f /usr/sbin/policy-rc.d
rm -rf /var/cache/*

dpkg-query -W '-f=${binary:Package}\t${Version}\t${Architecture}\t${db:Status-Status}\n' \
    | LC_ALL=C sort > /usr/share/101strap/packages.tsv
bash /tmp/101strap/seal-image.sh --image-root
