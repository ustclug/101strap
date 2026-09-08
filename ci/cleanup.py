"""Clean up recorded CI containers without disconnecting another build's disk."""

import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

NBD_DEVICE = "/dev/nbd0"
NBD_PID_FILE = Path("/sys/class/block/nbd0/pid")


class Cleanup:
    def __init__(self, directory, log):
        self.directory = directory
        self.log = log

    def run(self, command, *, output=None, combine_output=False, timeout=10):
        """Use GNU timeout to bound the command and its child processes."""
        try:
            return subprocess.run(
                ["timeout", str(timeout), *command],
                stdout=self.log if output is None else output,
                stderr=subprocess.STDOUT if combine_output else self.log,
                text=True,
                check=False,
            )
        except OSError as error:
            print(f"{command}: {error}", file=self.log, flush=True)
            return None

    def read_container_id(self, filename):
        path = self.directory / filename
        if not path.exists() or path.stat().st_size == 0:
            return None
        container_id = path.read_text().strip()
        if not re.fullmatch(r"[0-9a-f]{64}", container_id):
            raise ValueError(f"Invalid container ID in {path}")
        return container_id

    def container_exists(self, container_id, name):
        with (self.directory / f"{name}.json").open("w") as output:
            result = self.run(
                ["sudo", "docker", "inspect", container_id], output=output
            )
        return result is not None and result.returncode == 0

    def stop_container(self, container_id, name):
        with (self.directory / f"{name}.log").open("w") as output:
            self.run(
                ["sudo", "docker", "logs", container_id],
                output=output,
                combine_output=True,
            )
        # Docker sends SIGKILL if the entrypoint does not finish within 20 seconds.
        result = self.run(
            ["sudo", "docker", "stop", "--time", "20", container_id],
            timeout=30,
        )
        return result is not None and result.returncode == 0

    def owns_disk(self, container_id, pid):
        if pid is None:
            return False
        cgroup = self.run(
            ["sudo", "cat", f"/proc/{pid}/cgroup"], output=subprocess.PIPE
        )
        cmdline = self.run(
            ["sudo", "cat", f"/proc/{pid}/cmdline"], output=subprocess.PIPE
        )
        if cgroup is None or cmdline is None:
            return False
        return (
            cgroup.returncode == 0
            and cmdline.returncode == 0
            and container_id in cgroup.stdout
            and "/target/root.qcow2" in cmdline.stdout.split("\0")
        )

    def cleanup_assembly(self):
        container_id = self.read_container_id("container.cid")
        if container_id is None or not self.container_exists(container_id, "container"):
            return True

        pid = read_nbd_pid()
        owned_before_stop = self.owns_disk(container_id, pid)
        if not self.stop_container(container_id, "container"):
            return False

        # The container may already have detached NBD during shutdown. If it is
        # still attached, recheck both PID and ownership before disconnecting.
        if owned_before_stop and read_nbd_pid() == pid:
            if not self.owns_disk(container_id, pid):
                return False
            result = self.run(
                ["sudo", "qemu-nbd", "--disconnect", NBD_DEVICE], timeout=15
            )
            return result is not None and result.returncode == 0
        return True

    def cleanup_buildkit(self):
        container_id = self.read_container_id("buildkit.cid")
        if container_id is None or not self.container_exists(container_id, "buildkit"):
            return True
        return self.stop_container(container_id, "buildkit")

    def cleanup(self):
        print(datetime.now(timezone.utc).isoformat(), file=self.log, flush=True)
        self.run(["df", "-h"])
        self.run(["sudo", "docker", "ps", "-a", "--no-trunc"])
        self.run(["sudo", "docker", "system", "df"])

        success = True
        # Always attempt both cleanups; a builder failure must not hide an
        # assembly failure, and an assembly failure must not skip the builder.
        for operation in (self.cleanup_assembly, self.cleanup_buildkit):
            try:
                if not operation():
                    success = False
            except (OSError, ValueError) as error:
                print(f"{operation.__name__}: {error}", file=self.log, flush=True)
                success = False
        return success


def read_nbd_pid():
    try:
        pid = NBD_PID_FILE.read_text().strip()
    except OSError:
        return None
    return pid if re.fullmatch(r"[0-9]+", pid) else None


def main():
    runner_temp = os.environ.get("RUNNER_TEMP")
    if not runner_temp:
        raise SystemExit("RUNNER_TEMP is required")
    directory = Path(runner_temp) / "101strap"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "cleanup.log").open("a") as log:
        return 0 if Cleanup(directory, log).cleanup() else 1


if __name__ == "__main__":
    sys.exit(main())
