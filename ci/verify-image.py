"""Read-only offline acceptance checks; does not boot or execute guest binaries."""
import json
import pathlib
import subprocess
import sys
import tempfile

image = str(pathlib.Path(sys.argv[1]).resolve())
arch = sys.argv[2]
info = json.loads(subprocess.check_output(["qemu-img", "info", "--output=json", image]))
assert info["format"] == "qcow2" and info["virtual-size"] == 16 * 1024**3
with tempfile.TemporaryDirectory(prefix="101strap-inspect-") as directory:
    root = pathlib.Path(directory)
    files = {
        "release": "/etc/os-release",
        "sources": "/etc/apt/sources.list.d/ubuntu.sources",
        "status": "/var/lib/dpkg/status",
        "machine-id": "/etc/machine-id",
        "shadow": "/etc/shadow",
        "flatpak": "/var/lib/flatpak/repo/config",
        "build-info": "/usr/share/101strap/build-info.txt",
    }
    commands = [f'download {guest} "{root / name}"' for name, guest in files.items()]
    commands += ["readlink /var/lib/dbus/machine-id", "exists /var/lib/systemd/random-seed"]
    result = subprocess.check_output(
        ["guestfish", "--ro", "-a", image, "-m", "/dev/sda2"],
        input="\n".join(commands) + "\n", text=True,
    )
    assert result.splitlines() == ["/etc/machine-id", "false"], result
    assert (root / "machine-id").read_bytes() == b""
    assert 'VERSION_ID="26.04"' in (root / "release").read_text()
    sources = (root / "sources").read_text()
    mirror = "https://mirrors.ustc.edu.cn/" + ("ubuntu" if arch == "amd64" else "ubuntu-ports")
    assert [line for line in sources.splitlines() if line.startswith("URIs:")] == [f"URIs: {mirror}"] * 2
    assert "url=https://mirrors.ustc.edu.cn/flathub" in (root / "flatpak").read_text()
    metadata = (root / "build-info").read_text()
    assert f"architecture={arch}\n" in metadata
    assert "build_mirror_mode=upstream\n" in metadata
    accounts = [line.split(":") for line in (root / "shadow").read_text().splitlines()]
    user = next(row for row in accounts if row[0] == "ustc")
    assert user[2] == "0" and user[1].startswith("$")
    packages = {}
    for paragraph in (root / "status").read_text().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in paragraph.splitlines() if ": " in line and not line.startswith(" "))
        if fields.get("Status") == "install ok installed":
            packages[fields["Package"]] = fields
    assert packages["dpkg"]["Architecture"] == arch
    for name in "python3-venv shellcheck jq manpages manpages-dev openssh-client curl build-essential gdb git firefox firefox-l10n-zh-cn xubuntu-desktop-minimal linux-image-virtual".split():
        assert name in packages, name
print("PASS: virtual size, release, architecture, packages, delivered mirrors and sealed identity/password state")
