#!/bin/bash
# Assemble the disk in a libguestfs appliance; no host block devices or mounts.
set -euo pipefail

cd /srv
# shellcheck source=config.sh
source ./config.sh
WORKSPACE=/target

[[ -d "$WORKSPACE" ]]
if [[ -e "$WORKSPACE/root.qcow2" || -L "$WORKSPACE/root.qcow2" ]]; then
    echo "Refusing to overwrite $WORKSPACE/root.qcow2" >&2
    exit 1
fi
HOST_ARCH=$(dpkg --print-architecture)
case "$HOST_ARCH:$ARCH" in
    amd64:amd64|arm64:arm64|amd64:arm64) ;;
    *) echo "Unsupported assembly host/target: $HOST_ARCH/$ARCH" >&2; exit 1 ;;
esac
check_rootfs_metadata() {
    local field=$1 expected=$2
    if [[ "$(cat "/rootfs-build/$field")" != "$expected" ]]; then
        echo "Cached rootfs $field does not match $expected" >&2
        exit 1
    fi
}
check_rootfs_metadata architecture "$ARCH"
check_rootfs_metadata mirror-mode "$BUILD_MIRROR_MODE"
check_rootfs_metadata cache-epoch "$CACHE_EPOCH"
check_rootfs_metadata stage configured

work=$(mktemp -d /tmp/101strap-assemble.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Tar carries ownership and capabilities into the appliance without extracting
# files or creating guest device nodes on the host.
tar --numeric-owner --acls --xattrs --xattrs-include='*' --one-file-system \
    --exclude='./dev/*' --exclude='./proc/*' --exclude='./sys/*' \
    --exclude='./run/*' --exclude='./tmp/*' -C /rootfs -cpf "$work/rootfs.tar" .

{
    printf 'release=%s\nsuite=%s\narchitecture=%s\ndisk_size_mib=%s\n' "$RELEASE" "$SUITE" "$ARCH" "$DISK_SIZE_MIB"
    printf 'built_at_utc=%s\nsource_commit=%s\nsource_dirty=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${SOURCE_COMMIT:-unknown}" "${SOURCE_DIRTY:-unknown}"
    printf 'ubuntu_mirror=%s\nmozilla_mirror=%s\n' "$DELIVERY_UBUNTU_MIRROR" "$DELIVERY_MOZILLA_MIRROR"
    printf 'rootfs_image_id=%s\ncache_epoch=%s\nrootfs_built_at_utc=%s\n' "${ROOTFS_IMAGE_ID:-unknown}" "$CACHE_EPOCH" "$(cat /rootfs-build/built-at)"
    printf 'build_mirror_mode=%s\nbuild_ubuntu_mirror=%s\nbuild_mozilla_mirror=%s\n' "$BUILD_MIRROR_MODE" "$UBUNTU_MIRROR" "$MOZILLA_MIRROR"
} > "$WORKSPACE/build-info.txt"
sha256sum image/*.sh build.sh config.sh assets/xfce4-panel.xml \
    assets/seal-image.sh assets/export-vmware.sh assets/vmware.yaml \
    assets/toggle-hidpi rootfs/*.sh rootfs/Dockerfile.in rootfs/build.py \
    > "$WORKSPACE/build-sources.sha256"

# Guestfish partition boundaries are inclusive 512-byte sectors. Leave 1 MiB
# at either end of the disk, as in the original GPT layout.
esp_start=2048
root_start=$(((ESP_SIZE_MIB + 1) * 2048))
root_end=$(((DISK_SIZE_MIB - 1) * 2048 - 1))
export LIBGUESTFS_BACKEND=direct
export LIBGUESTFS_MEMSIZE=${LIBGUESTFS_MEMSIZE:-2048}
cat > "$work/assemble.fish" <<EOF_FISH
echo "Creating disk and starting the libguestfs appliance"
disk-create $WORKSPACE/root.qcow2 qcow2 $((DISK_SIZE_MIB * 1024 * 1024))
add-drive $WORKSPACE/root.qcow2 format:qcow2 discard:enable
run
part-init /dev/sda gpt
part-add /dev/sda p $esp_start $((root_start - 1))
part-add /dev/sda p $root_start $root_end
part-set-name /dev/sda 1 "EFI System"
part-set-name /dev/sda 2 "Linux system"
part-set-gpt-type /dev/sda 1 C12A7328-F81F-11D2-BA4B-00A0C93EC93B
mkfs ext4 /dev/sda2 inode:256 "label:Linux system"
mount /dev/sda2 /
echo "Importing the cached rootfs"
tar-in $work/rootfs.tar / xattrs:true acls:true
mkdir-p /boot/efi
mkdir-p /tmp/101strap
upload /srv/rootfs/config.sh /tmp/101strap/config.sh
upload /srv/image/finalize.sh /tmp/101strap/finalize.sh
upload /srv/assets/seal-image.sh /tmp/101strap/seal-image.sh
mkdir-p /usr/share/101strap
upload $WORKSPACE/build-info.txt /usr/share/101strap/build-info.txt
upload $WORKSPACE/build-sources.sha256 /usr/share/101strap/build-sources.sha256
EOF_FISH

command_prefix=
if [[ "$HOST_ARCH" != "$ARCH" ]]; then
    # These are static binaries for the appliance's architecture. Register
    # emulation there, independently of the host's binfmt configuration.
    cat >> "$work/assemble.fish" <<'EOF_FISH'
modprobe binfmt_misc
upload /bin/busybox /tmp/101strap/busybox
upload /usr/bin/qemu-aarch64 /tmp/101strap/qemu-aarch64
upload /srv/image/run-arm64.sh /tmp/101strap/run-arm64.sh
chmod 0755 /tmp/101strap/busybox
chmod 0755 /tmp/101strap/qemu-aarch64
EOF_FISH
    command_prefix='/tmp/101strap/busybox sh /tmp/101strap/run-arm64.sh '
fi

cat >> "$work/assemble.fish" <<EOF_FISH
command "${command_prefix}/usr/sbin/mkfs.fat -F32 -n EFI /dev/sda1"
mount-vfs iocharset=utf8 vfat /dev/sda1 /boot/efi
echo "Configuring boot files, delivery mirrors and image identity"
command "${command_prefix}/bin/bash /tmp/101strap/finalize.sh $ARCH"
# Set the delivered symlink after guestfish cleans up its temporary resolver.
rm-f /etc/resolv.conf
ln-s /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
download /usr/share/101strap/packages.tsv $WORKSPACE/packages.tsv
rm-rf /tmp/101strap
echo "Trimming filesystems and shutting down the appliance"
sync
fstrim /boot/efi
fstrim /
umount-all
shutdown
EOF_FISH

guestfish --network -f "$work/assemble.fish"
# Compress only after the appliance has exited and flushed the disk.
# Keep the original until conversion succeeds; rename on the same filesystem.
compressed_dir=$(mktemp -d "$WORKSPACE/.compress.XXXXXX")
trap 'rm -rf -- "$work" "$compressed_dir"' EXIT
echo "Compressing qcow2 with zlib"
qemu-img convert -p -f qcow2 -O qcow2 -c -o compression_type=zlib \
    "$WORKSPACE/root.qcow2" "$compressed_dir/root.qcow2"
qemu-img check "$compressed_dir/root.qcow2"
mv -f -- "$compressed_dir/root.qcow2" "$WORKSPACE/root.qcow2"
bash /srv/image/checksums.sh "$WORKSPACE"
