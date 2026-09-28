#!/bin/bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# shellcheck source=config.sh
source ./config.sh

if [[ -z "${CONTAINER_ENGINE:-}" ]]; then
    if command -v podman >/dev/null; then
        CONTAINER_ENGINE=podman
    else
        CONTAINER_ENGINE=docker
    fi
fi
command -v "$CONTAINER_ENGINE" >/dev/null
OUTPUT_DIR="$PWD/dist/$ARCH"
if [[ -e "$OUTPUT_DIR" ]] && [[ -n "$(ls -A -- "$OUTPUT_DIR")" ]]; then
    echo "Output directory is not empty: $OUTPUT_DIR. Move the previous build before retrying." >&2
    exit 1
fi

case "$(uname -m):$ARCH" in
    x86_64:amd64|aarch64:arm64|x86_64:arm64) ;;
    *) echo "Unsupported build host/target: $(uname -m)/$ARCH" >&2; exit 1 ;;
esac

stage=configured
if [[ "$FORMAT" == all ]]; then
    stage=exporter
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
export ARCH BUILD_MIRROR_MODE CACHE_EPOCH
rootfs_options=()
if [[ -n "${BUILDER_CIDFILE:-}" ]]; then
    rootfs_options+=(--builder-cidfile "$BUILDER_CIDFILE")
fi
python3 rootfs/build.py --engine "$CONTAINER_ENGINE" --target "$stage" \
    --tag "local/101strap:$stage" "${rootfs_options[@]}"
ROOTFS_IMAGE_ID=$("$CONTAINER_ENGINE" image inspect --format '{{.Id}}' "local/101strap:$stage")

container_options=()
if [[ -n "${BUILD_CONTAINER_NAME:-}" ]]; then
    container_options+=(--name "$BUILD_CONTAINER_NAME")
fi
if [[ -n "${BUILD_CONTAINER_CIDFILE:-}" ]]; then
    container_options+=(--cidfile "$BUILD_CONTAINER_CIDFILE")
fi
if [[ -r /dev/kvm && -w /dev/kvm ]]; then
    container_options+=(--device /dev/kvm)
    if [[ "$CONTAINER_ENGINE" == podman ]]; then
        container_options+=(--group-add keep-groups)
    fi
fi
"$CONTAINER_ENGINE" run --init --rm "${container_options[@]}" \
    -v "$PWD:/srv:ro" -v "$OUTPUT_DIR:/target" \
    -e "LIBGUESTFS_BACKEND_SETTINGS=${LIBGUESTFS_BACKEND_SETTINGS:-}" \
    -e "LIBGUESTFS_MEMSIZE=${LIBGUESTFS_MEMSIZE:-2048}" \
    -e "BUILD_MIRROR_MODE=$BUILD_MIRROR_MODE" -e "ARCH=$ARCH" -e "FORMAT=$FORMAT" \
    -e "ROOTFS_IMAGE_ID=$ROOTFS_IMAGE_ID" -e "CACHE_EPOCH=$CACHE_EPOCH" -e "SOURCE_COMMIT=$SOURCE_COMMIT" -e "SOURCE_DIRTY=$SOURCE_DIRTY" \
    "$ROOTFS_IMAGE_ID"
