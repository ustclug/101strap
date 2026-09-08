"""Cache boundaries and metadata-preserving guest filesystem transfer."""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class RootfsTests(unittest.TestCase):
    def run_builder(self, *, engine_name="docker", cache_mode="gha", desktop_status=0):
        """Run the real entry point with a container command that records stages."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sudo = root / "sudo"
            sudo.write_text(
                """#!/bin/bash
if [[ "$1" == --preserve-env=* ]]; then
    shift
fi
exec "$@"
"""
            )
            sudo.chmod(0o755)
            container_engine = root / engine_name
            container_engine.write_text("""#!/bin/bash
if [[ "$1 $2" == 'buildx inspect' ]]; then
    exit 0
fi
printf '%s\\n' "$*" >> "$TEST_CALLS"
while (( $# )); do
    if [[ "$1" == --target ]]; then
        stage=$2
        break
    fi
    shift
done
if [[ "$stage" == desktop ]]; then
    exit "$TEST_DESKTOP_STATUS"
fi
""")
            container_engine.chmod(0o755)
            env = {
                **os.environ,
                "PATH": directory + ":" + os.environ["PATH"],
                "TEST_CALLS": str(root / "calls"),
                "CONTAINER_CACHE": cache_mode,
                "TEST_DESKTOP_STATUS": str(desktop_status),
                "BUILD_MIRROR_MODE": "upstream",
                "ACTIONS_RUNTIME_TOKEN": "fixture",
                "ACTIONS_RESULTS_URL": "https://example.invalid",
                "ARCH": "amd64",
                "FORMAT": "qcow2",
                "CACHE_EPOCH": "0",
            }
            env.pop("RUNNER_TEMP", None)
            result = subprocess.run(
                ["python3", str(REPO / "rootfs/build.py"), "--engine", engine_name],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            calls = (root / "calls").read_text().splitlines()
            return result, calls

    def test_failed_stage_stops_pipeline_and_retries_without_import(self):
        result, calls = self.run_builder(desktop_status=42)
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertEqual(len(calls), 4)
        self.assertIn("--target image", calls[0])
        self.assertIn("--target bootstrap", calls[1])
        self.assertIn("--target desktop", calls[2])
        self.assertIn("--cache-from", calls[2])
        self.assertNotIn("--cache-from", calls[3])
        self.assertIn("--cache-to", calls[3])
        self.assertNotIn("--load", "\n".join(calls))

    def test_interruption_is_not_retried(self):
        for status in (130, 143):
            with self.subTest(status=status):
                result, calls = self.run_builder(desktop_status=status)
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertEqual(len(calls), 3)
                self.assertIn("--target desktop", calls[-1])

    def test_success_tags_only_the_final_stage(self):
        for engine_name, cache_mode in (("docker", "gha"), ("podman", "local")):
            with self.subTest(engine=engine_name):
                result, calls = self.run_builder(
                    engine_name=engine_name,
                    cache_mode=cache_mode,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--target configured", calls[-1])
                self.assertIn("-t local/101strap:rootfs", calls[-1])
                for call in calls[:-1]:
                    self.assertNotIn("-t local/101strap:rootfs", call)
                if engine_name == "docker":
                    self.assertIn("--load", calls[-1])
                else:
                    self.assertNotIn("--cache-from", "\n".join(calls))

    def test_copy_metadata_and_exclude_runtime_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            target = Path(directory) / "target"
            target.mkdir()
            for name in ("etc", "dev", "proc", "sys", "run", "tmp"):
                (source / name).mkdir(parents=True)
            data = source / "etc/data"
            data.write_text("persistent")
            data.chmod(0o640)
            os.link(data, source / "etc/hardlink")
            (source / "etc/symlink").symlink_to("data")
            os.setxattr(data, "user.test", b"preserved")
            for name in ("dev", "proc", "sys", "run", "tmp"):
                (source / name / "transient").write_text("must not copy")
            subprocess.run(
                ["bash", str(REPO / "rootfs/copy.sh"), str(source), str(target)],
                check=True,
            )
            output = target / "etc/data"
            self.assertEqual(output.read_text(), "persistent")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o640)
            self.assertEqual(output.stat().st_uid, data.stat().st_uid)
            self.assertEqual(
                output.stat().st_ino, (target / "etc/hardlink").stat().st_ino
            )
            self.assertEqual(os.readlink(target / "etc/symlink"), "data")
            self.assertEqual(os.getxattr(output, "user.test"), b"preserved")
            for name in ("dev", "proc", "sys", "run", "tmp"):
                self.assertFalse((target / name / "transient").exists())
