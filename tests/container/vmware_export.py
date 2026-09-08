"""Run in the exporter image, or with qemu-img and open-vmdk installed."""

import hashlib
import json
import subprocess
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OVF = "http://schemas.dmtf.org/ovf/envelope/1"
VMW = "http://www.vmware.com/schema/ovf"


class VMwareExportTests(unittest.TestCase):
    def test_archive_preserves_disk_and_describes_efi_guest(self):
        with tempfile.TemporaryDirectory(prefix="101strap-ova-test-") as directory:
            workspace = Path(directory)
            raw_disk = workspace / "source.raw"
            # Nonzero data on either side of a hole catches conversion mistakes
            # that a completely empty disk would miss.
            with raw_disk.open("wb") as disk:
                disk.write(b"first sector" * 40)
                disk.seek(8 * 1024 * 1024 - 512)
                disk.write(b"last sector" * 40)
                disk.truncate(8 * 1024 * 1024)
            source_disk = workspace / "source.vmdk"
            subprocess.run(
                [
                    "qemu-img",
                    "convert",
                    "-f",
                    "raw",
                    "-O",
                    "vmdk",
                    str(raw_disk),
                    str(source_disk),
                ],
                check=True,
            )
            output = workspace / "test-vm.ova"
            command = [
                "bash",
                str(REPO / "assets/export-vmware.sh"),
                str(source_disk),
                str(output),
            ]
            subprocess.run(command, check=True)

            with tarfile.open(output) as archive:
                self.assertEqual(
                    archive.getnames(),
                    ["test-vm.ovf", "test-vm.mf", "root.vmdk"],
                )
                for member in archive.getmembers():
                    self.assertTrue(member.isfile(), member.name)
                descriptor = archive.extractfile("test-vm.ovf").read()
                manifest = archive.extractfile("test-vm.mf").read().decode()
                for filename in ("test-vm.ovf", "root.vmdk"):
                    with archive.extractfile(filename) as stream:
                        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
                    self.assertIn(f"SHA256({filename})= {checksum}", manifest)
                exported_disk = workspace / "exported.vmdk"
                exported_disk.write_bytes(archive.extractfile("root.vmdk").read())

            envelope = ET.fromstring(descriptor)
            settings = {
                item.get(f"{{{VMW}}}key"): item.get(f"{{{VMW}}}value")
                for item in envelope.iter(f"{{{VMW}}}Config")
            }
            self.assertEqual(settings["firmware"], "efi")
            self.assertEqual(settings["bootOptions.efiSecureBootEnabled"], "false")
            disk = envelope.find(f"{{{OVF}}}DiskSection/{{{OVF}}}Disk")
            self.assertTrue(disk.get(f"{{{OVF}}}format").endswith("#streamOptimized"))
            disk_info = json.loads(
                subprocess.check_output(
                    ["qemu-img", "info", "--output=json", str(exported_disk)],
                    text=True,
                )
            )
            self.assertEqual(disk_info["virtual-size"], raw_disk.stat().st_size)
            subprocess.run(
                [
                    "qemu-img",
                    "compare",
                    "-f",
                    "raw",
                    "-F",
                    "vmdk",
                    str(raw_disk),
                    str(exported_disk),
                ],
                check=True,
            )

            original_archive = output.read_bytes()
            result = subprocess.run(command, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), original_archive)

            source_disk.write_text("invalid VMDK")
            failed_output = workspace / "failed.ova"
            result = subprocess.run(
                command[:-1] + [str(failed_output)],
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(failed_output.exists())
            self.assertEqual(list(workspace.glob(".vmware-export.*")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
