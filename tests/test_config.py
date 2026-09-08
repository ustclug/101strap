"""Mirror selection must preserve local defaults and reject ambiguous input."""

import os
import pathlib
import subprocess
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def config(self, arch, mode=None):
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in ("ARCH", "FORMAT", "BUILD_MIRROR_MODE")
        }
        env["ARCH"] = arch
        if mode is not None:
            env["BUILD_MIRROR_MODE"] = mode
        return subprocess.run(
            [
                "bash",
                "-ec",
                'source config.sh; printf "%s\\n" "$BUILD_MIRROR_MODE" "$FORMAT" "$DELIVERY_UBUNTU_MIRROR"; write_ubuntu_sources "$UBUNTU_MIRROR" "$UBUNTU_SECURITY_MIRROR"',
            ],
            cwd=REPO,
            env=env,
            capture_output=True,
            check=False,
            text=True,
        )

    def test_defaults(self):
        for arch, path, fmt in [
            ("amd64", "ubuntu", "all"),
            ("arm64", "ubuntu-ports", "qcow2"),
        ]:
            result = self.config(arch)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(
                result.stdout.startswith(
                    f"ustc\n{fmt}\nhttps://mirrors.ustc.edu.cn/{path}\n"
                )
            )
            self.assertEqual(
                result.stdout.count(f"URIs: https://mirrors.ustc.edu.cn/{path}\n"), 2
            )

    def test_upstream(self):
        for arch, main, security in [
            ("amd64", "archive.ubuntu.com/ubuntu", "security.ubuntu.com/ubuntu"),
            ("arm64", "ports.ubuntu.com/ubuntu-ports", "ports.ubuntu.com/ubuntu-ports"),
        ]:
            result = self.config(arch, "upstream")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                f"URIs: https://{main}\nSuites: resolute resolute-updates\n",
                result.stdout,
            )
            self.assertIn(
                f"URIs: https://{security}\nSuites: resolute-security\n", result.stdout
            )
            self.assertIn("https://mirrors.ustc.edu.cn/ubuntu", result.stdout)

    def test_invalid(self):
        result = self.config("amd64", "invalid")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsupported BUILD_MIRROR_MODE", result.stderr)
