"""Exercise failure boundaries without privileged devices or a container daemon."""

import os
import pathlib
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]


class CIFailureTests(unittest.TestCase):
    def test_logging_preserves_failure_and_skips_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "101strap").mkdir()
            (root / "build.sh").write_text("echo diagnostic-marker; exit 42\n")
            qemu_img = root / "qemu-img"
            qemu_img.write_text("#!/bin/bash\ntouch verification-reached\n")
            qemu_img.chmod(0o755)
            environment = {
                **os.environ,
                "RUNNER_TEMP": directory,
                "ARCH": "amd64",
                "PATH": directory + ":" + os.environ["PATH"],
            }
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'source "$1"; run_build_and_verify',
                    "bash",
                    str(REPO / "ci/build.sh"),
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 42)
            self.assertIn(
                "diagnostic-marker", (root / "101strap/build.log").read_text()
            )
            self.assertFalse((root / "verification-reached").exists())

    def test_cleanup_without_owned_container_does_not_stop_or_detach(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            sudo = root / "sudo"
            sudo.write_text(
                '#!/bin/bash\nprintf "%s\\n" "$*" >> "$RUNNER_TEMP/calls"\nexit 0\n'
            )
            sudo.chmod(0o755)
            result = subprocess.run(
                ["python3", str(REPO / "ci/cleanup.py")],
                env={
                    **os.environ,
                    "RUNNER_TEMP": directory,
                    "PATH": directory + ":" + os.environ["PATH"],
                },
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (root / "calls").read_text()
            self.assertNotIn("stop", calls)
            self.assertNotIn("disconnect", calls)
            self.assertTrue((root / "101strap/cleanup.log").is_file())
