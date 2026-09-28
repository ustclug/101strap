"""Launch a disposable QEMU session for a built qcow2 image."""

import argparse
import os
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Platform:
    emulator: str
    machine: str
    host_architecture: str
    graphics: tuple[str, ...]
    graphics_gl: tuple[str, ...]
    firmware_pairs: tuple[tuple[str, str], ...]


PLATFORMS = {
    "amd64": Platform(
        emulator="qemu-system-x86_64",
        machine="q35",
        host_architecture="x86_64",
        graphics=("-vga", "virtio"),
        graphics_gl=("-device", "virtio-vga-gl"),
        firmware_pairs=(
            (
                "/usr/share/edk2/x64/OVMF_CODE.4m.fd",
                "/usr/share/edk2/x64/OVMF_VARS.4m.fd",
            ),
            ("/usr/share/OVMF/OVMF_CODE_4M.fd", "/usr/share/OVMF/OVMF_VARS_4M.fd"),
        ),
    ),
    "arm64": Platform(
        emulator="qemu-system-aarch64",
        machine="virt",
        host_architecture="aarch64",
        graphics=("-device", "virtio-gpu-pci"),
        graphics_gl=("-device", "virtio-gpu-gl-pci"),
        firmware_pairs=(
            (
                "/usr/share/edk2/aarch64/QEMU_EFI.fd",
                "/usr/share/edk2/aarch64/QEMU_VARS.fd",
            ),
            ("/usr/share/AAVMF/AAVMF_CODE.fd", "/usr/share/AAVMF/AAVMF_VARS.fd"),
        ),
    ),
}


def find_firmware(platform):
    code = os.environ.get("FIRMWARE_CODE")
    variables = os.environ.get("FIRMWARE_VARS")
    candidates = [(code, variables)] if code or variables else platform.firmware_pairs
    for code, variables in candidates:
        if (
            code
            and variables
            and os.access(code, os.R_OK)
            and os.access(variables, os.R_OK)
        ):
            return Path(code), Path(variables)
    raise ValueError(
        "Set FIRMWARE_CODE and FIRMWARE_VARS to a matching pair of UEFI firmware files."
    )


def qemu_command(platform, *, disk, firmware_code, firmware_variables, acceleration):
    cpu = "host" if acceleration == "kvm" else "max"
    display = os.environ.get("QEMU_DISPLAY", "gtk,gl=on")
    opengl = display.split(",")[0] == "egl-headless" or "gl=on" in display.split(",")
    return [
        platform.emulator,
        "-machine",
        f"{platform.machine},accel={acceleration}",
        "-cpu",
        cpu,
        "-smp",
        "2",
        "-m",
        "4096",
        "-drive",
        f"if=pflash,format=raw,unit=0,readonly=on,file={firmware_code}",
        "-drive",
        f"if=pflash,format=raw,unit=1,file={firmware_variables}",
        "-drive",
        f"if=virtio,format=qcow2,file={disk}",
        "-snapshot",
        "-netdev",
        "user,id=net101",
        "-device",
        "virtio-net-pci,netdev=net101",
        *(platform.graphics_gl if opengl else platform.graphics),
        "-device",
        "qemu-xhci",
        "-device",
        "usb-kbd",
        "-device",
        "usb-tablet",
        "-display",
        display,
        "-serial",
        "mon:stdio",
    ]


def launch(architecture):
    platform = PLATFORMS[architecture]
    disk = REPO / "dist" / architecture / "root.qcow2"
    if not os.access(disk, os.R_OK):
        raise ValueError(f"Cannot read disk: {disk}")
    if shutil.which(platform.emulator) is None:
        raise ValueError(f"QEMU executable not found: {platform.emulator}")
    firmware_code, firmware_variables = find_firmware(platform)

    native_host = os.uname().machine == platform.host_architecture
    acceleration = (
        "kvm" if native_host and os.access("/dev/kvm", os.R_OK | os.W_OK) else "tcg"
    )
    print(
        f"Testing {architecture} with {acceleration}; disk changes will be discarded on exit.",
        flush=True,
    )
    with tempfile.TemporaryDirectory(prefix="101strap-vm-") as directory:
        disposable_variables = Path(directory) / "vars.fd"
        shutil.copyfile(firmware_variables, disposable_variables)
        command = qemu_command(
            platform,
            disk=disk,
            firmware_code=firmware_code,
            firmware_variables=disposable_variables,
            acceleration=acceleration,
        )
        return run_vm(command)


def run_vm(command):
    with subprocess.Popen(command) as process:
        try:
            return process.wait()
        except BaseException:
            # Stop QEMU before deleting its writable firmware copy.
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise


def terminate(signum, frame):
    raise SystemExit(128 + signum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=PLATFORMS, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, terminate)
    try:
        status = launch(args.arch)
        return status if status >= 0 else 128 - status
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
