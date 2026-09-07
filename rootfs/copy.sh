#!/bin/bash
# Copy an offline rootfs without crossing mounts or losing Unix metadata.
set -euo pipefail
source_root=${1:?}
target_root=${2:?}
test -d "$source_root/etc"
test -d "$target_root"
tar --numeric-owner --acls --xattrs --xattrs-include='*' --one-file-system \
    --exclude='./dev/*' --exclude='./proc/*' --exclude='./sys/*' \
    --exclude='./run/*' --exclude='./tmp/*' -C "$source_root" -cpf - . \
    | tar --numeric-owner --same-owner --same-permissions --acls --xattrs \
        --xattrs-include='*' -C "$target_root" -xpf -
