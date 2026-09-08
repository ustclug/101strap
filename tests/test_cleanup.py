"""Verify cleanup ownership decisions without touching host devices."""

import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ci import cleanup

CONTAINER_ID = "a" * 64


class CleanupTests(unittest.TestCase):
    def test_disconnect_requires_ownership_before_and_after_stop(self):
        cases = (
            ("owned", ["42", "42"], [True, True], True, True),
            ("different container", ["42"], [False], True, False),
            ("PID changed", ["42", "43"], [True], True, False),
            ("ownership changed", ["42", "42"], [True, False], False, False),
        )
        for name, pids, ownership, success, disconnect in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                (workspace / "container.cid").write_text(CONTAINER_ID)
                cleaner = cleanup.Cleanup(workspace, io.StringIO())
                with (
                    patch.object(cleaner, "container_exists", return_value=True),
                    patch.object(cleaner, "stop_container", return_value=True),
                    patch.object(cleaner, "owns_disk", side_effect=ownership),
                    patch.object(cleanup, "read_nbd_pid", side_effect=pids),
                    patch.object(
                        cleaner, "run", return_value=subprocess.CompletedProcess([], 0)
                    ) as run,
                ):
                    self.assertEqual(cleaner.cleanup_assembly(), success)
                    if disconnect:
                        run.assert_called_once_with(
                            ["sudo", "qemu-nbd", "--disconnect", "/dev/nbd0"],
                            timeout=15,
                        )
                    else:
                        run.assert_not_called()

    def test_disk_path_must_be_a_complete_command_argument(self):
        cleaner = cleanup.Cleanup(Path("/unused"), io.StringIO())
        for disk_path, owned in (
            ("/target/root.qcow2", True),
            ("/target/root.qcow2.other", False),
        ):
            with self.subTest(path=disk_path):
                cgroup = subprocess.CompletedProcess(
                    [], 0, stdout=f"0::/docker/{CONTAINER_ID}\n"
                )
                cmdline = subprocess.CompletedProcess(
                    [], 0, stdout=f"qemu-nbd\0{disk_path}\0"
                )
                with patch.object(cleaner, "run", side_effect=[cgroup, cmdline]):
                    self.assertEqual(cleaner.owns_disk(CONTAINER_ID, "42"), owned)

    def test_builder_cleanup_runs_even_if_assembly_record_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "container.cid").write_text("invalid")
            cleaner = cleanup.Cleanup(workspace, io.StringIO())
            with (
                patch.object(cleaner, "run"),
                patch.object(
                    cleaner, "cleanup_buildkit", return_value=True
                ) as buildkit,
            ):
                self.assertFalse(cleaner.cleanup())
                buildkit.assert_called_once()
