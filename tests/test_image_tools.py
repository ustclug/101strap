"""Unprivileged regression tests: python3 -m unittest discover -s tests."""

import pathlib
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]


class ImageToolsTests(unittest.TestCase):
    def test_partition_geometry(self):
        with tempfile.TemporaryDirectory(prefix="101strap-geometry-") as directory:
            disk = pathlib.Path(directory) / "disk.raw"
            disk_size_mib = 16384
            esp_size_mib = 256
            with disk.open("wb") as stream:
                stream.truncate(disk_size_mib * 1024 * 1024)
            subprocess.run(
                [
                    "bash",
                    str(REPO / "assets/partition-image.sh"),
                    str(disk),
                    str(disk_size_mib),
                    str(esp_size_mib),
                ],
                check=True,
                capture_output=True,
            )
            output = subprocess.check_output(
                ["parted", "-ms", str(disk), "unit", "B", "print"], text=True
            )
            partitions = {
                row.split(":")[0]: row.split(":")
                for row in output.splitlines()
                if row[:1].isdigit()
            }
            self.assertEqual(
                partitions["1"][1:4], ["1048576B", "269484031B", "268435456B"]
            )
            self.assertEqual(
                partitions["2"][1:4], ["269484032B", "17178820607B", "16909336576B"]
            )

    def test_checksums(self):
        with tempfile.TemporaryDirectory(prefix="101strap-checksums-") as directory:
            output = pathlib.Path(directory)
            for name in (
                "root.qcow2",
                "packages.tsv",
                "build-info.txt",
                "build-sources.sha256",
            ):
                (output / name).write_text(name)
            command = ["bash", str(REPO / "101strap_checksums"), directory]
            subprocess.run(command, check=True)
            subprocess.run(
                ["sha256sum", "-c", "SHA256SUMS"],
                cwd=output,
                check=True,
                capture_output=True,
            )
            (output / "VirtualBox-Xubuntu-26.04-amd64.ova").write_text("export")
            subprocess.run(command, check=True)
            self.assertEqual(len((output / "SHA256SUMS").read_text().splitlines()), 5)
            (output / "root.qcow2").write_text("modified")
            self.assertNotEqual(
                subprocess.run(
                    ["sha256sum", "-c", "SHA256SUMS"],
                    cwd=output,
                    capture_output=True,
                    check=False,
                ).returncode,
                0,
            )
            previous = (output / "SHA256SUMS").read_bytes()
            (output / "root.vdi").symlink_to(output / "root.qcow2")
            self.assertNotEqual(
                subprocess.run(command, capture_output=True, check=False).returncode, 0
            )
            self.assertEqual((output / "SHA256SUMS").read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
