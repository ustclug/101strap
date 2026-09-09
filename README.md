# 101strap

## Introduction

This project aims to automate the generation of XUbuntu, which will be used as an example in [linux101](https://101.lug.ustc.edu.cn/). This project developed by [taoky](https://github.com/taoky), [RTXUX](https://github.com/RTXUX), and [xuao1](https://github.com/xuao1).

## Build

The scripts generate Ubuntu **26.04 (Resolute)** with the Xubuntu minimal desktop. Build on Linux with Docker (including Buildx) or Podman and root access to NBD devices. The wrapper uses `sudo` when needed and prefers Docker if installed; set `CONTAINER_ENGINE=podman` to choose Podman explicitly.

```sh
# amd64: qcow2, VMDK, VDI, and VMware/VirtualBox OVA
./build.sh

# amd64: qcow2 only
ARCH=amd64 FORMAT=qcow2 ./build.sh

# arm64: qcow2 for QEMU / UTM
ARCH=arm64 ./build.sh
```

Outputs are in `build101/<arch>/`, including `root.qcow2`, build metadata and `SHA256SUMS`. Run `sha256sum -c SHA256SUMS` in that directory to verify them. A nonempty output directory is rejected; move the previous build aside before retrying.

The image has a sparse 16 GiB virtual disk and uses UEFI without Secure Boot. The username and initial password are both `ustc`; the password must be changed on first login. Ubuntu, Flathub and the Mozilla APT repository use USTC mirrors.

**Note:**

- The exporter container includes [open-vmdk](https://github.com/vmware/open-vmdk) and VirtualBox to generate the respective OVA files; no host export tools are required.

- If OVA export fails, you can import the generated VMDK into VMware Workstation or VDI into VirtualBox and export it manually.

- NBD defaults to `/dev/nbd0`; set `NBD` to select another unused device. Do not run concurrent builds on the same device.

- For an arm64 build on x86_64, install a static QEMU user emulator and enable the host's `qemu-aarch64` binfmt handler with the **F flag**. Native arm64 builds do not need emulation.

- For development notes, see [Devlog-2023-03-29.md](archived/Devlog-2023-03-29.md).

### Project layout

- `build.sh` and `config.sh`: host build entry point and settings.
- `rootfs/`: cached root filesystem construction.
- `image/`: container entry point, disk assembly, exports and checksums.
- `assets/`: guest configuration and image helpers.
- `ci/`: build orchestration, verification and cleanup for GitHub Actions.
- `tools/run-vm.py`: disposable QEMU launcher.

### Cache

Completed rootfs stages are cached, so retries can reuse installed packages. Builds check for updates to the Ubuntu 26.04 base image; a changed base invalidates dependent layers. Change `CACHE_EPOCH` to refresh tools and guest packages; keep the same value for subsequent retries. Disk assembly always creates a new image.

```sh
CACHE_EPOCH=refresh-1 ARCH=amd64 FORMAT=qcow2 ./build.sh

# Build only the rootfs, without allocating a disk.
ARCH=amd64 python3 rootfs/build.py --engine docker --target configured
```

Docker uses a project-specific Buildx builder named `101strap`; set `BUILDX_BUILDER` to use another builder configured with the `security.insecure` entitlement. Podman uses rootful layered builds. See [config.sh](config.sh) for build settings.

### GitHub Actions

Pushes and pull requests run static checks. To build images, open **Actions → qcow2 images → Run workflow**. The workflow builds qcow2 images on native amd64 and arm64 runners. Keep the cache epoch unchanged to reuse packages, or change it to refresh them.

Download `101strap-qcow2-amd64` or `101strap-qcow2-arm64` from the run's Artifacts section and verify `SHA256SUMS` after extracting. Images and diagnostic logs are retained for seven days. CI uses upstream mirrors during construction and restores USTC mirrors in the delivered image. Hosted builds and remote cache restoration still need rollout validation.

## Run

Install QEMU system emulators and matching UEFI firmware, then run:

```sh
python3 tools/run-vm.py --arch amd64
python3 tools/run-vm.py --arch arm64
```

The launcher uses 2 CPUs and 4 GiB RAM, with KVM when available and TCG otherwise. If firmware is not detected, set `FIRMWARE_CODE` and `FIRMWARE_VARS` to a matching pair. Changes to the disk and UEFI variables are discarded when QEMU exits.

For Apple Silicon UTM, use the QEMU backend with ARM64 (`aarch64`), the `virt` machine, UEFI enabled and Secure Boot disabled. Import `build101/arm64/root.qcow2` as a VirtIO disk, with a VirtIO GPU without 3D acceleration, a VirtIO NIC and USB keyboard/tablet. UTM compatibility still needs validation on a Mac.

## Manual verification

Before publishing, check first-login password changes, desktop login, networking, Firefox, Chinese input, shutdown and reboot. Boot two independently imported VMs and verify that their machine IDs differ and remain stable across reboots.
