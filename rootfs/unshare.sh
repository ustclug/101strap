#!/bin/bash
# Keep all mounts and binfmt registrations inside this stage's namespaces.
set -euo pipefail

# Preserve every container UID/GID, including package and desktop accounts.
# Mapping only the current user to root would break chown during installation.
exec unshare --user --map-users=all --map-groups=all \
    --mount --uts --ipc --fork --kill-child \
    bash /recipe/run-stage.sh "$@"
