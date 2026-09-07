"""Build cached guest stages with Docker BuildKit or rootful Podman."""
import argparse
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STAGES = ("image", "bootstrap", "desktop", "applications", "kernel", "configured")


def render(engine):
    tools = (REPO / "Dockerfile").read_text().split("\nFROM image AS exporter")[0]
    template = (REPO / "rootfs/Dockerfile.in").read_text()
    run = "RUN --security=insecure" if engine == "docker" else "RUN"
    syntax = "# syntax=docker/dockerfile:1.14-labs\n" if engine == "docker" else ""
    return syntax + template.replace("@TOOLS@", tools.rstrip()).replace("@RUN@", run)


def build_command(engine, prefix, dockerfile, stage, arch, mode, epoch, tag, builder, scope):
    command = prefix + [engine]
    if engine == "docker":
        command += ["buildx", "build", "--builder", builder, "--allow", "security.insecure", "--progress=plain"]
        if scope:
            command += ["--cache-from", f"type=gha,version=2,scope={scope}",
                        "--cache-to", f"type=gha,version=2,scope={scope},mode=max,ignore-error=true"]
        if tag:
            command += ["--load", "-t", tag]
        else:
            command += ["--output=type=cacheonly"]
    else:
        command += ["build", "--layers", "--cap-add=SYS_ADMIN", "--cap-add=MKNOD", "--security-opt=seccomp=unconfined",
                    "--security-opt=label=disable"]
        if tag:
            command += ["-t", tag]
    command += ["-f", dockerfile, "--target", stage,
                "--build-arg", f"ARCH={arch}", "--build-arg", f"BUILD_MIRROR_MODE={mode}",
                "--build-arg", f"CACHE_EPOCH={epoch}", str(REPO)]
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("docker", "podman"), required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--target", choices=(*STAGES, "exporter"), default="configured")
    parser.add_argument("--tag", default="local/101strap:rootfs")
    args = parser.parse_args()
    if args.render:
        print(render(args.engine), end="")
        return
    # Use the same validated config as the host wrapper, without shell interpolation.
    values = subprocess.check_output(
        ["bash", "-ec", 'source ./config.sh; printf "%s\\n" "$ARCH" "$BUILD_MIRROR_MODE" "$CACHE_EPOCH"'],
        cwd=REPO, text=True,
    ).splitlines()
    arch, mode, epoch = values
    cache = os.environ.get("CONTAINER_CACHE", "local")
    if cache not in ("local", "gha") or (cache == "gha" and args.engine != "docker"):
        parser.error("CONTAINER_CACHE must be local, or gha with Docker")
    prefix = [] if os.geteuid() == 0 else ["sudo"]
    if cache == "gha":
        for name in ("ACTIONS_RUNTIME_TOKEN", "ACTIONS_RESULTS_URL"):
            if not os.environ.get(name):
                parser.error(f"{name} must be exposed to use the Actions cache")
        if prefix:
            prefix += ["--preserve-env=ACTIONS_RUNTIME_TOKEN,ACTIONS_RESULTS_URL"]
    engine = prefix + [args.engine]
    builder = os.environ.get("BUILDX_BUILDER", "101strap")
    if args.engine == "docker" and subprocess.run(
        engine + ["buildx", "inspect", builder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    ).returncode:
        subprocess.run(engine + ["buildx", "create", "--name", builder, "--driver", "docker-container",
                                 "--buildkitd-flags", "--allow-insecure-entitlement security.insecure"], check=True)
    # Record the exact disposable CI daemon before any guest stage starts.
    if args.engine == "docker" and os.environ.get("RUNNER_TEMP"):
        subprocess.run(engine + ["buildx", "inspect", "--bootstrap", builder], check=True)
        cid = subprocess.check_output(engine + ["inspect", "--format", "{{.Id}}", f"buildx_buildkit_{builder}0"], text=True).strip()
        logs = Path(os.environ["RUNNER_TEMP"]) / "101strap"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "buildkit.cid").write_text(cid + "\n")
    scope = f"101strap-v1-{os.uname().machine}-{arch}-{mode}" if cache == "gha" else None
    stages = list(STAGES)
    if args.target == "exporter":
        stages.append("exporter")
    else:
        stages = stages[:stages.index(args.target) + 1]
    # A stable context and only stage-specific COPY inputs preserve cache locality.
    with tempfile.TemporaryDirectory(prefix="101strap-recipe-") as directory:
        dockerfile = str(Path(directory) / "Dockerfile")
        Path(dockerfile).write_text(render(args.engine))
        for stage in stages:
            start = time.monotonic()
            print(f"=== rootfs stage {stage}: start ===", flush=True)
            command = build_command(args.engine, prefix, dockerfile, stage, arch, mode, epoch,
                                    args.tag if stage == args.target else None, builder, scope)
            print(shlex.join(command), flush=True)
            status = subprocess.run(command, check=False).returncode
            if status and scope and status not in (-2, -15, 130, 143):
                # Cache import failures are not consistently nonfatal across BuildKit versions.
                # Retry without the importer; a real build failure still fails on this attempt.
                print("Build/cache import failed; retrying using local layers only", file=sys.stderr, flush=True)
                index = command.index("--cache-from")
                del command[index:index + 2]
                status = subprocess.run(command, check=False).returncode
            print(f"=== rootfs stage {stage}: status={status}, seconds={time.monotonic() - start:.1f} ===", flush=True)
            if status:
                raise SystemExit(status)


if __name__ == "__main__":
    main()
