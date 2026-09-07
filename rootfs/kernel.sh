#!/bin/bash
# Sourced only by rootfs/run-stage.sh.
# shellcheck disable=SC2034,SC2154
inspkg linux-image-virtual "$GRUB_PACKAGE" initramfs-tools cloud-initramfs-growroot
