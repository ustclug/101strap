"""Cache boundaries and metadata-preserving guest filesystem transfer."""
import importlib.util
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rootfs_build", REPO / "rootfs/build.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class RootfsTests(unittest.TestCase):
    def test_engine_permissions_and_shared_recipe(self):
        docker = builder.render("docker")
        podman = builder.render("podman")
        self.assertEqual(docker.count("RUN --security=insecure"), 5)
        self.assertNotIn("--security=insecure", podman)
        self.assertEqual(docker.split("\n", 1)[1].replace("RUN --security=insecure", "RUN"), podman)
        self.assertNotIn("COPY . ", docker)
        early, configured = docker.split("FROM kernel AS configured")
        self.assertNotIn("assets/", early)
        self.assertIn("assets/configure-panel.py", configured)
        self.assertNotIn("COPY config.sh", docker)

    def test_cumulative_remote_cache_and_final_load(self):
        command = builder.build_command("docker", [], "/tmp/Dockerfile", "desktop", "arm64", "upstream", "refresh1", None, "builder1", "scope1")
        self.assertIn("type=gha,version=2,scope=scope1,mode=max,ignore-error=true", command)
        self.assertIn("--output=type=cacheonly", command)
        self.assertIn("ARCH=arm64", command)
        self.assertIn("CACHE_EPOCH=refresh1", command)
        final = builder.build_command("docker", [], "/tmp/Dockerfile", "configured", "arm64", "upstream", "refresh1", "image1", "builder1", "scope1")
        self.assertIn("--load", final)
        self.assertNotIn("--output=type=cacheonly", final)
        podman = builder.build_command("podman", [], "/tmp/Dockerfile", "configured", "amd64", "ustc", "0", "image1", "", None)
        self.assertIn("--layers", podman)
        self.assertIn("--cap-add=MKNOD", podman)
        self.assertNotIn("--cache-to", podman)

    def test_epoch_validation_and_no_geometry_in_rootfs_config(self):
        env = {**os.environ, "CACHE_EPOCH": "bad value"}
        result = subprocess.run(["bash", "-ec", "source config.sh"], cwd=REPO, env=env, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        config = (REPO / "rootfs/config.sh").read_text()
        for name in ("FORMAT=", "DISK_SIZE_MIB=", "SOURCE_COMMIT", "SOURCE_DIRTY"):
            self.assertNotIn(name, config)

    def test_failed_stage_stops_pipeline_and_retries_without_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sudo = root / "sudo"
            sudo.write_text('#!/bin/bash\nif [[ "$1" == --preserve-env=* ]]; then shift; fi\nexec "$@"\n')
            sudo.chmod(0o755)
            docker = root / "docker"
            docker.write_text("""#!/bin/bash
if [[ "$1 $2" == 'buildx inspect' ]]; then exit 0; fi
printf '%s\\n' "$*" >> "$TEST_CALLS"
while (( $# )); do
    if [[ "$1" == --target ]]; then stage=$2; break; fi
    shift
done
[[ "$stage" != desktop ]] || exit 42
""")
            docker.chmod(0o755)
            env = {**os.environ, "PATH": directory + ":" + os.environ["PATH"],
                   "TEST_CALLS": str(root / "calls"), "CONTAINER_CACHE": "gha",
                   "ACTIONS_RUNTIME_TOKEN": "fixture", "ACTIONS_RESULTS_URL": "https://example.invalid",
                   "ARCH": "amd64", "FORMAT": "qcow2", "CACHE_EPOCH": "0"}
            env.pop("RUNNER_TEMP", None)
            result = subprocess.run(["python3", str(REPO / "rootfs/build.py"), "--engine", "docker"],
                                    env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 42, result.stderr)
            calls = (root / "calls").read_text().splitlines()
            self.assertEqual(len(calls), 4)
            self.assertIn("--target image", calls[0])
            self.assertIn("--target bootstrap", calls[1])
            self.assertIn("--target desktop", calls[2])
            self.assertIn("--cache-from", calls[2])
            self.assertNotIn("--cache-from", calls[3])
            self.assertNotIn("--load", "\n".join(calls))

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
            subprocess.run(["bash", str(REPO / "rootfs/copy.sh"), str(source), str(target)], check=True)
            output = target / "etc/data"
            self.assertEqual(output.read_text(), "persistent")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o640)
            self.assertEqual(output.stat().st_uid, data.stat().st_uid)
            self.assertEqual(output.stat().st_ino, (target / "etc/hardlink").stat().st_ino)
            self.assertEqual(os.readlink(target / "etc/symlink"), "data")
            self.assertEqual(os.getxattr(output, "user.test"), b"preserved")
            for name in ("dev", "proc", "sys", "run", "tmp"):
                self.assertFalse((target / name / "transient").exists())
