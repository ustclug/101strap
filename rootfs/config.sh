#!/bin/bash
# Variables are consumed by the scripts sourcing this file.
# shellcheck disable=SC2034

# Shared by the host wrapper and the container entry points.
RELEASE=26.04
SUITE=resolute
# Use one complete repository for Firefox and its architecture-independent l10n packages.
MOZILLA_MIRROR=https://packages.mozilla.org/apt
BUILD_MIRROR_MODE=${BUILD_MIRROR_MODE:-ustc}
case "$BUILD_MIRROR_MODE" in
    ustc|upstream) ;;
    *) echo "Unsupported BUILD_MIRROR_MODE: $BUILD_MIRROR_MODE (expected ustc or upstream)" >&2; exit 1 ;;
esac
ARCH=${ARCH:-amd64}
case "$ARCH" in
    amd64)
        UBUNTU_MIRROR=https://mirrors.ustc.edu.cn/ubuntu
        GRUB_TARGET=x86_64-efi
        GRUB_PACKAGE=grub-efi-amd64
        ;;
    arm64)
        UBUNTU_MIRROR=https://mirrors.ustc.edu.cn/ubuntu-ports
        GRUB_TARGET=arm64-efi
        GRUB_PACKAGE=grub-efi-arm64
        ;;
    *) echo "Unsupported ARCH: $ARCH (expected amd64 or arm64)" >&2; exit 1 ;;
esac
DELIVERY_UBUNTU_MIRROR=$UBUNTU_MIRROR
if [[ "$BUILD_MIRROR_MODE" == upstream ]]; then
    case "$ARCH" in
        amd64) UBUNTU_MIRROR=https://archive.ubuntu.com/ubuntu ;;
        arm64) UBUNTU_MIRROR=https://ports.ubuntu.com/ubuntu-ports ;;
    esac
fi
UBUNTU_SECURITY_MIRROR=$UBUNTU_MIRROR
if [[ "$BUILD_MIRROR_MODE:$ARCH" == upstream:amd64 ]]; then
    UBUNTU_SECURITY_MIRROR=https://security.ubuntu.com/ubuntu
fi

write_ubuntu_sources() {
    cat <<EOF
Types: deb
URIs: $1
Suites: $SUITE $SUITE-updates
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: $2
Suites: $SUITE-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
}
