# Technical design

101strap builds a guest root filesystem in container layers, then copies it onto a new virtual disk. Package installation can reuse cached layers while each disk gets its own filesystems and boot configuration.

## Build flow

1. [build.sh](build.sh) reads the configuration, selects Docker or Podman, and checks the host architecture and output directory.
2. [rootfs/build.py](rootfs/build.py) renders the container recipe and builds the rootfs stages through `configured`.
3. The host starts an ordinary container with the repository and output directory mounted. If available, `/dev/kvm` is passed through for acceleration.
4. [image/build.sh](image/build.sh) runs disk assembly. For `FORMAT=all`, the host then builds the independent `exporter` image and runs [image/export.sh](image/export.sh) in a second container.

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
| `exporter` | Build an independent tools image for VMware and VirtualBox exports. |

The `open-vmdk-build` stage builds a pinned source archive and supplies tools to `exporter`. Both derive from `image` and have no dependency on the guest rootfs stages. `--target exporter` builds only `image` and `exporter`, with open-vmdk built as a dependency. Exporter uses a separate remote cache scope.

[rootfs/unshare.sh](rootfs/unshare.sh) gives each stage its own user, mount, UTS and IPC namespaces. It maps all container UIDs/GIDs unchanged into the child namespace, so package accounts and file ownership survive between layers. The container supplies PID isolation. [rootfs/run-stage.sh](rootfs/run-stage.sh) provides `ROOT`, `chdo` and `inspkg` to the stage scripts, which it sources into the same shell.

Bootstrap extracts packages with debootstrap's foreign stage on both architectures, prepares runtime mounts and `policy-rc.d`, then runs the second stage. This ensures guest package scripts use the same mounts as later stages.

During package installation, the guest sees basic character devices and recursive binds of the container's `/proc` and read-only `/sys`. Recursive binds preserve locked submounts inherited from the container. Cleanup detaches each mount tree as a unit; the stage namespace exits before the layer is committed. `policy-rc.d` prevents guest services from starting. Each stage temporarily copies the builder's DNS configuration, then restores the guest's systemd-resolved symlink and removes transient files from `/run` and `/tmp`.

The rootfs lives at `/rootfs`. Stage metadata lives separately at `/rootfs-build`, including architecture, mirror mode, cache epoch and build time.

## Engines and caching

Podman is selected by default when installed. Run it as an ordinary user with rootless storage, unprivileged user namespaces enabled, and at least 65536 subordinate UIDs and GIDs in `/etc/subuid` and `/etc/subgid`. Podman uses the system's UID/GID mapping helpers to create its outer namespace; stage scripts use `unshare` inside it. The build disables container seccomp, AppArmor and SELinux confinement so the nested namespaces and mounts work, but adds no capabilities and never invokes sudo. Host policy must permit user namespaces. Tools inside the Ubuntu 26.04 container supply a recent util-linux with `--map-users=all` support.

Docker remains available via `CONTAINER_ENGINE=docker`, using a Buildx builder named `builder-101strap` by default. `BUILDX_BUILDER` selects another builder. This compatibility path still requires the `security.insecure` entitlement to let stage commands create namespaces and mounts; a rootful Docker daemon retains host privileges. Use rootless Podman for a build without a privileged daemon. Engine commands use the caller's existing access and never automatically elevate privileges.

Disk assembly runs in a libguestfs appliance inside an unprivileged container. The tools image includes its own kernel and QEMU, so it needs no host NBD devices or host filesystem mounts. `/dev/kvm` is passed through only when the caller has read/write access; Podman retains supplementary groups for this device (requires the crun runtime). Without KVM, the appliance uses TCG. Set `LIBGUESTFS_BACKEND_SETTINGS=force_tcg` to force software emulation and `LIBGUESTFS_MEMSIZE` to change its default 2048 MiB of RAM.

Stage-specific `COPY` instructions control cache invalidation. The repository remains the build context even though the rendered recipe is temporary. Builds check for an updated Ubuntu base image. Package repository changes alone do not invalidate an existing layer; change `CACHE_EPOCH` to refresh packages, then keep that value for retries.

```sh
CACHE_EPOCH=refresh-1 FORMAT=qcow2 ./build.sh

# Build the rootfs without allocating a disk.
ARCH=amd64 python3 rootfs/build.py --engine podman --target configured

# Inspect the generated recipe.
python3 rootfs/build.py --engine docker --render
```

`CONTAINER_CACHE=gha` enables Docker's GitHub Actions cache backend. It requires `ACTIONS_RUNTIME_TOKEN` and `ACTIONS_RESULTS_URL`; the workflow exposes these to the build process. Cache scopes include the host architecture, guest architecture and mirror mode. Failed builds retry once without importing the remote cache, except when interrupted; cache export remains enabled.

## Architecture and mirrors

Native builds support amd64 and arm64. Cross-building arm64 on x86_64 requires Linux 6.7 or newer for binfmt_misc in user namespaces. Each stage mounts a private binfmt_misc instance and registers the tools image's static QEMU AArch64 interpreter with `F`, keeping it available across chroot. Cleanup unmounts this instance; namespace teardown releases its rules and interpreter references. The host needs no binfmt registration or QEMU installation.

The libguestfs appliance has a separate kernel. For cross-assembly, [image/run-arm64.sh](image/run-arm64.sh) uses native static BusyBox to register a static AArch64 interpreter inside that appliance. It keeps binfmt_misc mounted for each guest command and unmounts it afterward. KVM accelerates the native appliance; ARM64 commands still use QEMU user emulation. Temporary emulation helpers are removed from the delivered image.

amd64 supports `FORMAT=all` and `FORMAT=qcow2`; arm64 supports qcow2 only. The amd64 desktop includes VMware and VirtualBox integration packages; arm64 includes `spice-vdagent`.

`BUILD_MIRROR_MODE=ustc` is the default. CI sets it to `upstream` for construction. Assembly restores USTC Ubuntu, Mozilla and Flathub mirrors in the delivered image and refreshes APT indexes.

## Disk assembly and exports

[image/assemble.sh](image/assemble.sh) verifies the cached rootfs metadata before allocating a disk. One guestfish session creates a GPT layout with a 256 MiB EFI system partition and an ext4 root partition on the 16 GiB disk, leaving 1 MiB at either end.

Tar export and guestfish `tar-in` preserve ownership, permissions, ACLs and extended attributes. The guest's `mkfs.fat` explicitly formats the EFI partition as FAT32. [image/finalize.sh](image/finalize.sh) runs inside the appliance's guest chroot: it writes UUID-based `fstab` entries, regenerates the initramfs and invokes the guest's GRUB 2 at the removable UEFI path without changing host NVRAM. QEMU user networking provides DNS and access to package mirrors.

After sealing and trimming the filesystems, assembly unmounts them and shuts down the appliance. It then compresses qcow2 clusters with zlib, checks the converted image and replaces the original before hashing or exporting. Conversion temporarily needs space for both images. The compressed qcow2 boots directly; subsequent guest writes use uncompressed clusters. Mounts and block devices exist only inside the appliance. The container runs with an init process for signal forwarding and child reaping; stopping it also stops its QEMU process. Failed builds leave the partial output directory for diagnosis and refuse to overwrite it on retry.

For `FORMAT=all`, [image/export.sh](image/export.sh) converts qcow2 to VMDK and VDI. open-vmdk creates a stream-optimized copy for the VMware OVA using [assets/vmware.yaml](assets/vmware.yaml); VirtualBox creates the other OVA. Checksums are refreshed after exports. If export fails, the standalone VMDK or VDI can be imported manually.

## Input methods

Xfce starts Fcitx 5 through `/etc/xdg/autostart/org.fcitx.Fcitx5.desktop` in both X11 and labwc Wayland sessions. The system `xinputrc` selects `none` so im-config does not start a second daemon or override the image's environment settings. LightDM's PAM session loads `XMODIFIERS`, `QT_IM_MODULE`, `QT_IM_MODULES` and `SDL_IM_MODULE` from `/etc/environment`.

Following the [Fcitx Wayland guide](https://fcitx-im.org/wiki/Using_Fcitx_5_on_Wayland), `GTK_IM_MODULE` stays unset: native GTK 3/4 Wayland clients use text-input-v3, while GTK configuration files and Xfce's `Gtk/IMModule` setting select fcitx for X11/XWayland. Qt 5 uses the fcitx module; the image's Qt 6 (6.8.2 or newer) tries Wayland first and falls back to fcitx. Applications bundling older Qt versions or their own input modules may need per-application overrides.

## Image identity and metadata

The `ustc` account starts with password `ustc` and can log in immediately. Users can change the password through the desktop or `passwd`.

[assets/seal-image.sh](assets/seal-image.sh) empties `/etc/machine-id`, points the D-Bus machine ID to it, removes random seeds, NetworkManager identity data and shell histories, and clears build log contents. It refuses to seal an image containing an SSH server because first-boot host-key generation is not implemented.

Each output directory contains:

- `build-info.txt`: release, architecture, source revision, mirrors and rootfs image metadata.
- `packages.tsv`: package versions, architectures and installation states.
- `build-sources.sha256`: hashes of build scripts and assets.
- `SHA256SUMS`: hashes of image artifacts and metadata.

The first three files are also installed under `/usr/share/101strap/` in the guest.

## CI and verification

[The workflow](.github/workflows/qcow2.yml) runs shell syntax checks and ShellCheck on pushes and pull requests. Manual runs build qcow2 images on native amd64 and arm64 runners. Image artifacts and diagnostic logs are retained for seven days.

[ci/build.sh](ci/build.sh) records resource usage and passes explicit container ID paths for cleanup. `BUILDER_CIDFILE` becomes `rootfs/build.py --builder-cidfile`; `BUILD_CONTAINER_CIDFILE` records the assembly container. [ci/cleanup.py](ci/cleanup.py) stops those recorded containers, including the optional export container recorded in `container.cid.export`. No host disk disconnection is needed.

Verification runs `qemu-img check`, [ci/verify-image.py](ci/verify-image.py) and checksum validation after the assembly container exits. The Python verifier uses guestfish to inspect the image offline, checking packages, boot files, mirrors, metadata, identity cleanup, removal of temporary helpers and password expiry.

Before publishing, boot the images and check desktop login, networking, Firefox, Chinese input, shutdown and reboot. Boot two independently imported VMs and confirm that machine IDs differ and remain stable across reboots. Hosted builds and remote cache restoration still need rollout validation.

## Local VM checks

[tools/run-vm.py](tools/run-vm.py) launches QEMU with 2 CPUs and 4 GiB RAM. It uses KVM when available on a matching host architecture and TCG otherwise. Disk changes are discarded on exit, and UEFI variables use a temporary copy. Set `FIRMWARE_CODE` and `FIRMWARE_VARS` to a matching pair if firmware discovery fails; `QEMU_DISPLAY` selects the display backend.

The default display is `gtk,gl=on`, with VirGL enabled through `virtio-vga-gl` on amd64 and `virtio-gpu-gl-pci` on arm64. This requires QEMU with OpenGL/virglrenderer support and a working host OpenGL driver. Set `QEMU_DISPLAY=gtk,gl=off` for 2D graphics, or `QEMU_DISPLAY=none` for a headless session without OpenGL. `QEMU_DISPLAY=egl-headless` keeps VirGL enabled without a window.

For Apple Silicon UTM, use its QEMU backend with ARM64 (`aarch64`), the `virt` machine, UEFI enabled and Secure Boot disabled. Import the qcow2 as a VirtIO disk and select a VirtIO GPU without 3D acceleration, a VirtIO NIC and USB keyboard/tablet. UTM compatibility still needs validation on a Mac.
