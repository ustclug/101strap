"""Stop the recorded assembly and BuildKit containers after a CI build."""

import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


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

    def cleanup_container(self, filename, name):
        container_id = self.read_container_id(filename)
        if container_id is None or not self.container_exists(container_id, name):
            return True
        return self.stop_container(container_id, name)

    def cleanup(self):
        print(datetime.now(timezone.utc).isoformat(), file=self.log, flush=True)
        self.run(["df", "-h"])
        self.run(["sudo", "docker", "ps", "-a", "--no-trunc"])
        self.run(["sudo", "docker", "system", "df"])

        success = True
        # Always attempt both cleanups; a builder failure must not hide an
        # assembly failure, and an assembly failure must not skip the builder.
        for filename, name in (
            ("container.cid", "container"),
            ("buildkit.cid", "buildkit"),
        ):
            try:
                if not self.cleanup_container(filename, name):
                    success = False
            except (OSError, ValueError) as error:
                print(f"{name}: {error}", file=self.log, flush=True)
                success = False
        return success


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
