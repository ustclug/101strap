"""Check firmware selection and disposable QEMU state without starting a VM."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import test_vm


class VMTests(unittest.TestCase):
    def test_partial_firmware_override_does_not_fall_back(self):
        with (
            patch.dict(
                os.environ, {"FIRMWARE_CODE": "/custom/code.fd", "FIRMWARE_VARS": ""}
            ),
            self.assertRaisesRegex(ValueError, "matching pair"),
        ):
            test_vm.find_firmware(test_vm.PLATFORMS["amd64"])

    def test_failed_emulator_preserves_original_firmware_and_removes_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            disk = workspace / "build101/arm64/root.qcow2"
            disk.parent.mkdir(parents=True)
            disk.write_bytes(b"original disk")
            firmware_code = workspace / "code.fd"
            firmware_variables = workspace / "vars.fd"
            firmware_code.write_bytes(b"firmware code")
            firmware_variables.write_bytes(b"original variables")
            copies = []

            def fake_qemu(command):
                self.assertEqual(command[0], "qemu-system-aarch64")
                self.assertIn("-snapshot", command)
                self.assertIn("virt,accel=tcg", command)
                variable_drive = next(arg for arg in command if "unit=1,file=" in arg)
                copied_variables = Path(variable_drive.split("file=", 1)[1])
                self.assertEqual(copied_variables.read_bytes(), b"original variables")
                copied_variables.write_bytes(b"changed by QEMU")
                copies.append(copied_variables)
                return 42

            with (
                patch.object(test_vm, "REPO", workspace),
                patch.object(
                    test_vm.shutil, "which", return_value="qemu-system-aarch64"
                ),
                patch.object(
                    test_vm.os,
                    "uname",
                    return_value=os.uname_result(("Linux", "test", "", "", "x86_64")),
                ),
                patch.dict(
                    os.environ,
                    {
                        "FIRMWARE_CODE": str(firmware_code),
                        "FIRMWARE_VARS": str(firmware_variables),
                    },
                ),
                patch.object(test_vm, "run_vm", side_effect=fake_qemu),
            ):
                self.assertEqual(test_vm.launch("arm64"), 42)
            self.assertFalse(copies[0].parent.exists())
            self.assertEqual(firmware_variables.read_bytes(), b"original variables")
            self.assertEqual(disk.read_bytes(), b"original disk")

    def test_termination_stops_qemu_before_returning(self):
        with patch.object(test_vm.subprocess, "Popen") as popen:
            process = popen.return_value.__enter__.return_value
            process.wait.side_effect = [SystemExit(143), 0]
            with self.assertRaises(SystemExit) as stopped:
                test_vm.run_vm(["qemu-system-aarch64"])
            self.assertEqual(stopped.exception.code, 143)
            process.terminate.assert_called_once()
            self.assertEqual(process.wait.call_args.kwargs, {"timeout": 5})
