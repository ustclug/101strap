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
            script = (REPO / "ci/build.sh").read_text()
            pipeline = next(line for line in script.splitlines() if line.startswith("bash build.sh 2>&1"))
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", pipeline + '\ntouch verification-reached'],
                cwd=root, env={**os.environ, "RUNNER_TEMP": directory}, capture_output=True,
            )
            self.assertEqual(result.returncode, 42)
            self.assertIn("diagnostic-marker", (root / "101strap/build.log").read_text())
            self.assertFalse((root / "verification-reached").exists())

    def test_cleanup_without_owned_container_does_not_stop_or_detach(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            sudo = root / "sudo"
            sudo.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$RUNNER_TEMP/calls"\nexit 0\n')
            sudo.chmod(0o755)
            result = subprocess.run(
                ["bash", str(REPO / "ci/cleanup.sh")],
                env={**os.environ, "RUNNER_TEMP": directory, "PATH": directory + ":" + os.environ["PATH"]},
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (root / "calls").read_text()
            self.assertNotIn("stop", calls)
            self.assertNotIn("disconnect", calls)
            self.assertTrue((root / "101strap/cleanup.log").is_file())
