# 101strap

Build Ubuntu 26.04 images with the Xubuntu minimal desktop for [Linux 101](https://101.lug.ustc.edu.cn/).

## Build

Requires Linux, Python 3, Docker with Buildx or Podman, and root access to NBD devices. The script uses `sudo` when needed. Set `CONTAINER_ENGINE=podman` to select Podman.

```sh
./build.sh                         # amd64: qcow2, VMDK, VDI and VMware/VirtualBox OVA
FORMAT=qcow2 ./build.sh             # amd64: qcow2 only
ARCH=arm64 ./build.sh               # arm64: qcow2
```

Outputs are in `build101/<arch>/`. Move previous builds aside before rebuilding; verify downloads with `sha256sum -c SHA256SUMS` in the output directory.

Use a native host for each architecture, or see [DESIGN.md](DESIGN.md) for cross-building. NBD defaults to `/dev/nbd0`; set `NBD` to choose another unused device.

GitHub Actions builds are available through **Actions → qcow2 images → Run workflow**. Download the `101strap-qcow2-amd64` or `101strap-qcow2-arm64` artifact.

## Run

Import the OVA into VMware or VirtualBox. For QEMU, install the system emulator and matching UEFI firmware, then run:

```sh
python3 tools/run-vm.py --arch amd64
python3 tools/run-vm.py --arch arm64
```

The QEMU launcher discards changes when it exits. Images use a 16 GiB disk and UEFI with Secure Boot disabled. The username and initial password are both `ustc`; change the password on first login.

## Further reading

- [Technical design and maintenance](DESIGN.md)
- [README before the 26.04 update](archived/README-24.04.md)
- [Development notes from 2023](archived/Devlog-2023-03-29.md)

Created by [taoky](https://github.com/taoky), [RTXUX](https://github.com/RTXUX), and [xuao1](https://github.com/xuao1).
