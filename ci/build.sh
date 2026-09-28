#!/bin/bash
# Run on a disposable native GitHub runner; logs must stay outside the checkout.
set -euo pipefail

run_build_and_verify() {
    bash build.sh 2>&1 | tee "$RUNNER_TEMP/101strap/build.log"
    qemu-img check "build101/$ARCH/root.qcow2"
    python3 ci/verify-image.py "build101/$ARCH/root.qcow2" "$ARCH"
    (cd "build101/$ARCH" && sha256sum -c SHA256SUMS)
}

finish() {
    local status=$?
    trap - EXIT
    if [[ -n "$monitor" ]]; then
        kill "$monitor" 2>/dev/null || true
        wait "$monitor" 2>/dev/null || true
    fi
    python3 ci/cleanup.py || status=1
    exit "$status"
}

main() {
    : "${RUNNER_TEMP:?}" "${ARCH:?}" "${BUILD_CONTAINER_NAME:?}"
    export BUILD_CONTAINER_CIDFILE="$RUNNER_TEMP/101strap/container.cid"
    export BUILDER_CIDFILE="$RUNNER_TEMP/101strap/buildkit.cid"
    export CONTAINER_ENGINE=docker FORMAT=qcow2 BUILD_MIRROR_MODE=upstream
    mkdir -p "$RUNNER_TEMP/101strap"
    monitor=
    trap finish EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    docker info
    case "$(uname -m):$ARCH" in
        x86_64:amd64|aarch64:arm64) ;;
        *)
            echo 'CI requires a native build host' >&2
            exit 1
            ;;
    esac
    # Both Docker storage and image output need room (usually the same filesystem).
    for directory in "$PWD" "$(docker info --format '{{.DockerRootDir}}')"; do
        available=$(df -B1 --output=avail "$directory" | tail -n 1)
        if (( available < ${MIN_FREE_GIB:-20} * 1024 * 1024 * 1024 )); then
            echo "Less than ${MIN_FREE_GIB:-20} GiB free (provisional layered-build threshold): $directory" >&2
            exit 1
        fi
    done
    (
        while true; do
            date -u
            df -h
            free -h
            du -sh build101 2>/dev/null || true
            timeout 10s docker system df || true
            timeout 10s docker buildx du --builder "${BUILDX_BUILDER:-101strap}" || true
            sleep 30
        done
    ) > "$RUNNER_TEMP/101strap/resources.log" 2>&1 &
    monitor=$!
    run_build_and_verify
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
