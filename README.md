# 101strap

## Introduction

This project aims to automate the generation of XUbuntu, which will be used as an example in [linux101](https://101.lug.ustc.edu.cn/). This project developed by [taoky](https://github.com/taoky), [RTXUX](https://github.com/RTXUX), and [xuao1](https://github.com/xuao1).

## Build

The scripts generate Ubuntu **26.04 (Resolute)** with the Xubuntu minimal
desktop. Build on Linux with Docker (with Buildx) or Podman and root access to NBD devices.
The wrapper uses `sudo` when needed and selects Docker if installed, otherwise
Podman. Set `CONTAINER_ENGINE=podman` to choose explicitly.

```sh
# amd64: qcow2, VMDK, VDI, and VMware/VirtualBox OVA
./build.sh

# amd64: qcow2 only; no OVF Tool or VirtualBox needed
ARCH=amd64 FORMAT=qcow2 ./build.sh

# arm64: qcow2 for QEMU / UTM (no OVA export)
ARCH=arm64 ./build.sh
```

Outputs are in `build101/amd64/` and `build101/arm64/`, with `root.qcow2`
in each directory. A nonempty output directory is rejected: move the previous
build aside before retrying. The disk has a sparse 16 GiB virtual capacity and uses
UEFI without Secure Boot. The username and initial password are both `ustc`.
On first login, the LightDM login screen requires the user to change the initial
password before entering the desktop. Follow its prompts for the current
password, a new password, and confirmation. Cancelling or failing the change
leaves it required at the next login; after success, subsequent logins use the
new password without repeating setup. Console logins enforce the same change.

The output directory also contains `build-info.txt` (release, architecture, build
time, source commit and dirty state), `packages.tsv` (package, version,
architecture and dpkg status), and `build-sources.sha256` (build recipe hashes).
These three files are also available inside the guest at `/usr/share/101strap/`.
Source commit/state are recorded by `build.sh`; direct container builds without
`SOURCE_COMMIT` and `SOURCE_DIRTY` record them as `unknown`.
`SHA256SUMS` covers the image and metadata, and is refreshed after successful OVA
export to include VMDK, VDI, VMX and OVA files. From the output directory, run
`sha256sum -c SHA256SUMS` to check them. Publish this checksum file through a
trusted channel; hashes alone do not authenticate a download.

Before sealing, the builder resets the machine ID and D-Bus ID, removes random
seed and NetworkManager identity/cache files, and clears shell histories and
build-time logs. systemd initializes the machine ID on boot. SSH server is not
preinstalled; sealing fails if one is installed without a host-key regeneration
mechanism. Imported VMs must receive fresh hypervisor UUIDs and MAC addresses
(choose “copied”, not “moved”, when asked by VMware).

Ubuntu packages use the USTC Ubuntu / Ubuntu Ports mirrors. Both architectures
use Mozilla's official APT repository for Firefox and its Chinese language pack.
Basic course tools include `python3-venv`, ShellCheck, `jq`, `manpages`,
`manpages-dev`, OpenSSH client and `curl`. No uv or project Python environment
is preinstalled.
Audio uses PipeWire with WirePlumber, the Xfce PulseAudio panel plugin, and
`pavucontrol`. The power-manager plugin is omitted from the VM's default panel.
Labwc and Xwayland are included for trying the experimental Xfce Wayland session;
the default X11 session is unchanged. Select the Xfce Wayland session at login,
or run `startxfce4 --wayland` from a TTY outside an existing desktop session
([Xfce testing instructions](https://wiki.xfce.org/releng/wayland_roadmap)).
The image sets `GDK_DISABLE=icon-nodes` globally in `/etc/environment` as a
temporary workaround for missing elementary-xfce symbolic icons in GTK 4
([upstream fix](https://github.com/shimmerproject/elementary-xfce/pull/541)).

For an arm64 build on x86_64, install a static QEMU user emulator and enable
the host's `qemu-aarch64` binfmt handler **with the F flag**. This allows the
emulator to run inside the container and target chroot. On an Arch Linux host
with `qemu-user-static` and its binfmt configuration installed:

```sh
sudo systemctl restart systemd-binfmt
cat /proc/sys/fs/binfmt_misc/qemu-aarch64
```

The output must contain `enabled` and `flags:` including `F`. Native arm64
builds do not need emulation. NBD defaults to `/dev/nbd0`; use `NBD=/dev/nbd1`
to select another unused device. Builds sharing an NBD device must not run
concurrently.

**Note:**

- For the complete amd64 export, install the "OVF Tool for Linux Zip" [from Broadcom](https://developer.broadcom.com/tools/open-virtualization-format-ovf-tool/latest) in `/usr/lib/ovftool`, or set `OVFTOOL_PATH`. VirtualBox is installed in the `exporter` container stage. The `image` stage only contains qcow2 build dependencies.

- If there is any problems exporting to the ova file, you can also choose to manually export it using vmdk/vdi. You need to import the VMDK into VMware Workstation and configure it accordingly, import the VDI into VirtualBox and configure it accordingly, and then export each as an OVA.

- To export an existing amd64 qcow2 without rebuilding the disk:

  ```sh
  # Export an existing amd64 qcow2; all commands here run from the repository.
  sudo docker build --target exporter -t local/101strap:exporter .
  sudo docker run --rm -v "$PWD:/srv:ro" -v "$PWD/build101/amd64:/target" \
    -v /usr/lib/ovftool:/Ovftool:ro -e ARCH=amd64 \
    local/101strap:exporter /bin/bash /srv/101strap_disk
  ```

- If you want more information, see the Devlog.

## Layered rootfs builds and caching

The wrapper builds the guest filesystem inside a container image before creating
any disk. The cached stages are `bootstrap`, `desktop`, `applications`, `kernel`
and `configured`. They contain debootstrap, packages and guest configuration;
the builder's own tools live outside `/rootfs` and are not copied into the guest.
Each stage commits only after its temporary guest mounts have been unmounted.
Changing desktop assets rebuilds configuration without reinstalling packages.
Changing an earlier stage invalidates its descendants.

Docker builds require the Buildx plugin. The wrapper creates a persistent,
project-specific `docker-container` builder named `101strap`, with the
`security.insecure` entitlement required for chroot mounts. It does not change
your default builder. Set `BUILDX_BUILDER` to use another builder configured with
that entitlement. Podman uses rootful `--layers` builds with `SYS_ADMIN`, `MKNOD`
and the required security options. The wrapper uses sudo for both engines.
Rootless disk assembly is not supported. Local amd64-to-arm64 builds still
require the host binfmt handler described above; CI uses native hosts only.

```sh
# Reuse completed stages, even after a later build failed.
ARCH=amd64 FORMAT=qcow2 ./build.sh

# Explicitly refresh tools and guest packages; keep this value for later retries.
CACHE_EPOCH=refresh-1 ARCH=amd64 FORMAT=qcow2 ./build.sh

# Build just the rootfs, without allocating NBD or requiring an empty output dir.
ARCH=amd64 BUILD_MIRROR_MODE=upstream CACHE_EPOCH=refresh-1 \
  python3 rootfs/build.py --engine docker --target configured
```

`CACHE_EPOCH` defaults to `0` and accepts 1–64 letters, digits, dots, underscores
or hyphens. There is no scheduled refresh. Reusing a cache does not mean installed
packages are current; changing the epoch reruns repository operations. The tool
container's Ubuntu multi-architecture digest is pinned separately in `Dockerfile`
and must be updated explicitly when changing that base. Local cache pruning or
remote eviction causes a normal rebuild.

The final disk is always new: assembly copies persistent guest files with their
ownership, permissions, links, ACLs and extended attributes, creates fresh UUIDs,
writes fstab, regenerates initramfs and GRUB, refreshes USTC APT indexes, records
provenance, seals identities, and generates checksums after NBD detaches. Index
refresh does not upgrade cached packages. `build-info.txt` includes the loaded
rootfs image ID, cache epoch and cached rootfs construction time separately from
the current disk build time. A failed disk build can reuse all rootfs stages;
move its nonempty output directory aside before retrying. A failed command inside
a stage reruns that stage, not just the failed command.

## GitHub Actions qcow2 builds

Pushes and pull requests run Bash syntax, ShellCheck and Python regression tests.
Open **Actions → qcow2 images → Run workflow**, select the branch and cache epoch,
and trigger the build manually. Keep the epoch unchanged to reuse cached packages;
change it to refresh. After checks pass, independent native amd64
(`ubuntu-24.04`) and arm64 (`ubuntu-24.04-arm`) Docker jobs build qcow2 images,
with a 180-minute limit each. No emulation, OVA export or GitHub Release is used.
Initial dispatch remains a separate, explicitly authorized rollout step.

CI builds and exports cumulative BuildKit `type=gha,mode=max` cache after each
successful named stage, scoped by host platform, guest architecture and mirror
mode. Thus a later stage failure does not discard already uploaded stages.
The final stage is loaded for disk assembly. Cache export errors are diagnostic
warnings; a failed build/import is retried once without the remote importer to
allow cold construction when the cache service is unavailable. A repeated build
failure still fails the job. A cancellation before an upload completes cannot
guarantee that upload survives. Cache storage and eviction are subject to GitHub
repository limits; no paid capacity is enabled automatically.

Download `101strap-qcow2-amd64` or `101strap-qcow2-arm64` from the completed run's
Artifacts section. Extract the ZIP, enter the extracted directory, and run:

```sh
sha256sum -c SHA256SUMS
qemu-img info root.qcow2
```

Image artifacts include build metadata and checksums, use compression level 1,
and expire after **seven days**. Failed builds upload diagnostics, never partial
images or unsealed rootfs containers. `101strap-diagnostics-<arch>` contains
stage timings, build output, periodic disk/memory/container usage and cleanup
logs, also retained for seven days. CI keeps logs and generated Dockerfiles
outside the checkout so they do not dirty source provenance.

Local builds default to `BUILD_MIRROR_MODE=ustc`; Actions uses `upstream` for
Ubuntu and Flathub during construction. Mozilla remains official. Both modes
restore USTC Ubuntu and Flathub configuration before sealing and strictly refresh
APT indexes against USTC, requiring USTC connectivity even on a cache hit.
`build-info.txt` separates construction mirrors from delivered sources.

`BUILD_CONTAINER_NAME` optionally names the assembly container;
`BUILD_CONTAINER_CIDFILE` records its exact ID. CI also tracks its disposable
BuildKit daemon ID, collects diagnostics and performs bounded cleanup. Cleanup
is best effort if the runner disappears; it never disconnects an NBD without
attributing its process to the recorded assembly container.

The layered build provisionally requires **20 GiB** free on the output and Docker
filesystems (`MIN_FREE_GIB` overrides the CI preflight). This is **not a measured
sufficient budget**: layers, unpacked images and qcow2 coexist. The first cold and
warm builds on both native runners must measure stage/transfer time and peak disk
usage and adjust this threshold. No preinstalled runner software is deleted.

Local validation has exercised all amd64 rootfs stages with Podman, complete warm
cache reuse, desktop-resource invalidation and failure/retry behavior. A disposable
BuildKit 0.20.2 daemon also passed bootstrap cold and warm builds. Container
fixtures verified sealing and metadata transfer, including ACLs and capabilities.
These were isolated rootless-container tests of the stages, not a validation of
rootless disk assembly or a hosted Actions run.

CI checks detached NBD, `qemu-img check`, 16 GiB virtual capacity, checksums and
the offline guest's release, architecture, course tools, mirrors, identity and
password state before upload. Docker execution on the hosted runners, cross-run
remote cache restoration and both complete native disk builds require rollout
validation; local container tests do not establish graphical boot, password-change
UI behavior or independent-VM identity. Those remain the manual tests below.

## Run

Install QEMU system emulators and matching UEFI firmware, then run:

```sh
ARCH=amd64 bash test-vm.sh
ARCH=arm64 bash test-vm.sh
```

The launcher uses 2 CPUs and 4 GiB RAM, selects KVM for a matching host when
accessible, and otherwise uses TCG (arm64 on x86_64 can be slow). It recognizes
Arch and Debian/Ubuntu firmware paths; otherwise set `FIRMWARE_CODE` and
`FIRMWARE_VARS` to a matching pair. `QEMU_DISPLAY=none` enables headless testing;
arm64 boot messages and login are available on the serial console. Press
Ctrl-A X to quit QEMU. The disk and UEFI variables are disposable during this
test: changes are discarded when QEMU exits.

For Apple Silicon UTM, create a Linux VM using the **QEMU backend** with
ARM64 (`aarch64`), the `virt` machine, UEFI enabled and Secure Boot disabled.
Import `build101/arm64/root.qcow2` as a VirtIO disk, select a VirtIO GPU without
3D acceleration, shared networking with a VirtIO NIC, and USB keyboard/tablet.
Start with 2 CPUs and 4 GiB RAM. SPICE guest tools are included. This is the
intended test configuration; UTM compatibility still needs a real Mac test.

After building, verify that first login requires a password change, cancellation
does not bypass it, and a subsequent login accepts the new password without
another change prompt. Then verify the version and architecture (`cat /etc/os-release`,
`dpkg --print-architecture`), desktop login, networking, Firefox, Chinese input,
`toggle-hidpi`, shutdown and reboot. Save build output with `2>&1 | tee
build-arm64.log` (enable `set -o pipefail` to preserve the build exit status).
On failure the builder unmounts its rootfs and disconnects its NBD; if unmounting
fails it leaves the NBD attached and reports that manual cleanup is needed.

For unprivileged partition-layout and checksum regression tests (requires
Python 3 and `parted`), run `python3 -m unittest discover -s tests -v`.
The destructive sealing fixture must only run in a disposable container:

```sh
podman run --rm --network=none -v "$PWD:/srv:ro" --entrypoint /bin/bash \
  local/101strap:configured /srv/tests/test_seal_container.sh
```

To verify numeric ownership, setuid/setgid modes, ACLs and capabilities during
rootfs transfer, run the same disposable-container command with
`/srv/tests/test_copy_container.sh` instead. Unprivileged regression tests cover
hardlinks, symlinks and ordinary extended attributes too.

Before publishing, boot two independently imported VMs and check that
`cat /etc/machine-id` differs between them but survives a reboot unchanged in
each VM. Also test first-login password changes and verify `SHA256SUMS` against
the unmodified release artifacts. These boot checks are separate from the
container tests.
