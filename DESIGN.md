# Technical design

101strap builds a guest root filesystem in container layers, then copies it onto a new virtual disk. Package installation can reuse cached layers while each disk gets its own filesystems and boot configuration.

## Build flow

1. [build.sh](build.sh) reads the configuration, selects Docker or Podman, and checks the host architecture and output directory.
2. [rootfs/build.py](rootfs/build.py) renders the container recipe and builds stages through `configured`, or `exporter` for `FORMAT=all`.
3. The host loads the NBD module and starts a privileged container with the repository, output directory and host `/dev` mounted.
4. [image/build.sh](image/build.sh) runs disk assembly and, when requested, the VMware and VirtualBox exports.

[config.sh](config.sh) defines disk size, output format and cache epoch. It sources [rootfs/config.sh](rootfs/config.sh), which defines the Ubuntu release, architecture-specific packages and mirrors.

## Root filesystem stages

[rootfs/Dockerfile.in](rootfs/Dockerfile.in) contains the complete container build graph. The renderer substitutes `@RUN@` with the syntax required by the selected engine.

| Stage | Purpose |
| --- | --- |
| `image` | Install tools used to build the rootfs and assemble disks. |
| `bootstrap` | Run debootstrap, configure APT and block package installation from starting guest services. |
| `desktop` | Install Xubuntu, course tools, language support and guest integration packages. |
| `applications` | Configure Flathub and install Firefox from Mozilla's APT repository. |
| `kernel` | Install the kernel, GRUB and initramfs tools. |
| `configured` | Apply the desktop layout, locale, user account, networking and boot settings. |
| `exporter` | Add VirtualBox and open-vmdk tools for OVA exports. |

The `open-vmdk-build` stage builds a pinned source archive and supplies tools to `exporter`.

[rootfs/run-stage.sh](rootfs/run-stage.sh) provides `ROOT`, `chdo` and `inspkg` to the stage scripts, which it sources into the same shell. It mounts the guest's runtime filesystems and unmounts them before the layer completes. Bootstrap creates the rootfs before requesting these mounts.

During package installation, the guest sees basic character devices and a read-only bind of `/sys`. `policy-rc.d` prevents guest services from starting. Each stage temporarily copies the builder's DNS configuration, then restores the guest's systemd-resolved symlink and removes transient files from `/run` and `/tmp`.

The rootfs lives at `/rootfs`. Stage metadata lives separately at `/rootfs-build`, including architecture, mirror mode, cache epoch and build time.

## Engines and caching

Docker uses a Buildx builder named `101strap` by default. `BUILDX_BUILDER` selects another builder; it must allow the `security.insecure` entitlement needed for mounts during rootfs construction. Podman uses rootful layered builds with the required capabilities.

Stage-specific `COPY` instructions control cache invalidation. The repository remains the build context even though the rendered recipe is temporary. Builds check for an updated Ubuntu base image. Package repository changes alone do not invalidate an existing layer; change `CACHE_EPOCH` to refresh packages, then keep that value for retries.

```sh
CACHE_EPOCH=refresh-1 FORMAT=qcow2 ./build.sh

# Build the rootfs without allocating a disk.
ARCH=amd64 python3 rootfs/build.py --engine docker --target configured

# Inspect the generated recipe.
python3 rootfs/build.py --engine docker --render
```

`CONTAINER_CACHE=gha` enables Docker's GitHub Actions cache backend. It requires `ACTIONS_RUNTIME_TOKEN` and `ACTIONS_RESULTS_URL`; the workflow exposes these to the build process. Cache scopes include the host architecture, guest architecture and mirror mode. Failed builds retry once without importing the remote cache, except when interrupted; cache export remains enabled.

## Architecture and mirrors

Native builds support amd64 and arm64. Cross-building arm64 on x86_64 requires a static QEMU user emulator and an enabled `qemu-aarch64` binfmt handler with the `F` flag. The scripts check this before starting the image build. Cross-bootstrap uses debootstrap's foreign and second stages.

amd64 supports `FORMAT=all` and `FORMAT=qcow2`; arm64 supports qcow2 only. The amd64 desktop includes VMware and VirtualBox integration packages; arm64 includes `spice-vdagent`.

`BUILD_MIRROR_MODE=ustc` is the default. CI sets it to `upstream` for construction. Assembly restores USTC Ubuntu, Mozilla and Flathub mirrors in the delivered image and refreshes APT indexes.

## Disk assembly and exports

[image/assemble.sh](image/assemble.sh) verifies the cached rootfs metadata before allocating a disk. [assets/partition-image.sh](assets/partition-image.sh) creates a GPT layout with a 256 MiB EFI system partition and an ext4 root partition on the 16 GiB disk, leaving 1 MiB at either end.

[rootfs/copy.sh](rootfs/copy.sh) copies persistent guest files with ownership, permissions, ACLs and extended attributes. Assembly writes UUID-based `fstab` entries, regenerates the initramfs and installs GRUB at the removable UEFI path without changing host NVRAM.

After sealing and trimming the filesystems, assembly unmounts them and disconnects NBD before hashing the output. Cleanup tracks mounts and the NBD connection; if unmounting fails, it leaves NBD connected for recovery. Use an unused device and do not run concurrent builds on the same NBD.

For `FORMAT=all`, [image/export.sh](image/export.sh) converts qcow2 to VMDK and VDI. open-vmdk creates a stream-optimized copy for the VMware OVA using [assets/vmware.yaml](assets/vmware.yaml); VirtualBox creates the other OVA. Checksums are refreshed after exports. If export fails, the standalone VMDK or VDI can be imported manually.

## Image identity and metadata

The `ustc` account starts with password `ustc` and an expired password flag, requiring a change on first login.

[assets/seal-image.sh](assets/seal-image.sh) empties `/etc/machine-id`, points the D-Bus machine ID to it, removes random seeds, NetworkManager identity data and shell histories, and clears build log contents. It refuses to seal an image containing an SSH server because first-boot host-key generation is not implemented.

Each output directory contains:

- `build-info.txt`: release, architecture, source revision, mirrors and rootfs image metadata.
- `packages.tsv`: package versions, architectures and installation states.
- `build-sources.sha256`: hashes of build scripts and assets.
- `SHA256SUMS`: hashes of image artifacts and metadata.

The first three files are also installed under `/usr/share/101strap/` in the guest.

## CI and verification

[The workflow](.github/workflows/qcow2.yml) runs shell syntax checks and ShellCheck on pushes and pull requests. Manual runs build qcow2 images on native amd64 and arm64 runners. Image artifacts and diagnostic logs are retained for seven days.

[ci/build.sh](ci/build.sh) records resource usage and passes explicit container ID paths for cleanup. `BUILDER_CIDFILE` becomes `rootfs/build.py --builder-cidfile`; `BUILD_CONTAINER_CIDFILE` records the assembly container. [ci/cleanup.py](ci/cleanup.py) uses those IDs and checks NBD ownership before attempting a disconnect.

Verification runs `qemu-img check`, [ci/verify-image.py](ci/verify-image.py) and checksum validation after NBD is detached. The Python verifier uses guestfish to inspect the image offline, checking packages, boot files, mirrors, metadata, identity cleanup and password expiry.

Before publishing, boot the images and check password changes, desktop login, networking, Firefox, Chinese input, shutdown and reboot. Boot two independently imported VMs and confirm that machine IDs differ and remain stable across reboots. Hosted builds and remote cache restoration still need rollout validation.

## Local VM checks

[tools/run-vm.py](tools/run-vm.py) launches QEMU with 2 CPUs and 4 GiB RAM. It uses KVM when available on a matching host architecture and TCG otherwise. Disk changes are discarded on exit, and UEFI variables use a temporary copy. Set `FIRMWARE_CODE` and `FIRMWARE_VARS` to a matching pair if firmware discovery fails; `QEMU_DISPLAY` selects the display backend.

For Apple Silicon UTM, use its QEMU backend with ARM64 (`aarch64`), the `virt` machine, UEFI enabled and Secure Boot disabled. Import the qcow2 as a VirtIO disk and select a VirtIO GPU without 3D acceleration, a VirtIO NIC and USB keyboard/tablet. UTM compatibility still needs validation on a Mac.
