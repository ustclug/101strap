#!/bin/bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# shellcheck source=config.sh
source ./config.sh

if [[ -z "${CONTAINER_ENGINE:-}" ]]; then
    if command -v docker >/dev/null; then
        CONTAINER_ENGINE=docker
    else
        CONTAINER_ENGINE=podman
    fi
fi
command -v "$CONTAINER_ENGINE" >/dev/null
OVFTOOL_PATH=${OVFTOOL_PATH:-/usr/lib/ovftool}
NBD=${NBD:-/dev/nbd0}
if [[ ! "$NBD" =~ ^/dev/nbd[0-9]+$ ]]; then
    echo "NBD must name a /dev/nbdN device: $NBD" >&2
    exit 1
fi
OUTPUT_DIR="$PWD/build101/$ARCH"
if [[ -e "$OUTPUT_DIR" ]] && [[ -n "$(ls -A -- "$OUTPUT_DIR")" ]]; then
    echo "Output directory is not empty: $OUTPUT_DIR. Move the previous build before retrying." >&2
    exit 1
fi
if [[ "$FORMAT" == all && ! -x "$OVFTOOL_PATH/ovftool" ]]; then
    echo "Missing $OVFTOOL_PATH/ovftool. Set OVFTOOL_PATH or use FORMAT=qcow2." >&2
    exit 1
fi

emulation_volumes=()
case "$(uname -m):$ARCH" in
    x86_64:amd64|aarch64:arm64) ;;
    x86_64:arm64)
        if ! grep -q '^enabled$' /proc/sys/fs/binfmt_misc/qemu-aarch64 2>/dev/null ||
           ! grep -q '^flags:.*F' /proc/sys/fs/binfmt_misc/qemu-aarch64; then
            echo "Cross-building requires an enabled qemu-aarch64 binfmt handler with the F flag on the host." >&2
            exit 1
        fi
        emulation_volumes=(-v /proc/sys/fs/binfmt_misc:/proc/sys/fs/binfmt_misc:ro)
        ;;
    *) echo "Unsupported build host/target: $(uname -m)/$ARCH" >&2; exit 1 ;;
esac

privilege=()
if (( EUID != 0 )); then
    privilege=(sudo)
fi
# Loading an already loaded module is harmless; never unload other users' NBDs.
"${privilege[@]}" modprobe nbd max_part=16
if [[ ! -b "$NBD" ]]; then
    echo "NBD is not a block device: $NBD" >&2
    exit 1
fi
if [[ -s "/sys/class/block/${NBD##*/}/pid" ]]; then
    echo "NBD is already connected: $NBD" >&2
    exit 1
fi

stage=image
volumes=()
if [[ "$FORMAT" == all ]]; then
    stage=exporter
    volumes=(-v "$OVFTOOL_PATH:/Ovftool:ro")
fi
mkdir -p -- "$OUTPUT_DIR"
SOURCE_COMMIT=unknown
SOURCE_DIRTY=unknown
if command -v git >/dev/null && git rev-parse --verify HEAD >/dev/null 2>&1; then
    SOURCE_COMMIT=$(git rev-parse HEAD)
    SOURCE_DIRTY=false
    if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
        SOURCE_DIRTY=true
    fi
fi
"${privilege[@]}" "$CONTAINER_ENGINE" build --build-arg "BUILD_MIRROR_MODE=$BUILD_MIRROR_MODE" --target "$stage" -t "local/101strap:$stage" .
container_options=()
if [[ -n "${BUILD_CONTAINER_NAME:-}" ]]; then
    container_options+=(--name "$BUILD_CONTAINER_NAME")
fi
if [[ -n "${BUILD_CONTAINER_CIDFILE:-}" ]]; then
    container_options+=(--cidfile "$BUILD_CONTAINER_CIDFILE")
fi
"${privilege[@]}" "$CONTAINER_ENGINE" run --privileged --rm "${container_options[@]}" \
    -v "$PWD:/srv:ro" -v "$OUTPUT_DIR:/target" -v /dev:/dev \
    "${volumes[@]}" "${emulation_volumes[@]}" \
    -e "BUILD_MIRROR_MODE=$BUILD_MIRROR_MODE" -e "NBD=$NBD" -e "ARCH=$ARCH" -e "FORMAT=$FORMAT" \
    -e "SOURCE_COMMIT=$SOURCE_COMMIT" -e "SOURCE_DIRTY=$SOURCE_DIRTY" \
    "local/101strap:$stage"
