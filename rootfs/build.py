"""Build cached guest stages in user namespaces with Podman or Docker BuildKit."""

import argparse
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STAGES = ("image", "bootstrap", "desktop", "applications", "kernel", "configured")
INTERRUPTED_STATUSES = (-2, -15, 130, 143)


@dataclass(frozen=True)
class GuestConfig:
    architecture: str
    mirror_mode: str
    cache_epoch: str


@dataclass(frozen=True)
class BuildConfig:
    engine_name: str
    engine_command: list[str]
    dockerfile: Path
    guest: GuestConfig
    builder_name: str
    cache_scope: str | None


def read_guest_config():
    # Source the same validated configuration as the host wrapper.
    script = (
        'source ./config.sh; printf "%s\\n" "$ARCH" "$BUILD_MIRROR_MODE" "$CACHE_EPOCH"'
    )
    output = subprocess.check_output(
        ["bash", "-ec", script],
        cwd=REPO,
        text=True,
    )
    architecture, mirror_mode, cache_epoch = output.splitlines()
    return GuestConfig(architecture, mirror_mode, cache_epoch)


def render(engine_name):
    template = (REPO / "rootfs/Dockerfile.in").read_text()
    if engine_name == "docker":
        run_instruction = "RUN --security=insecure"
        syntax_directive = "# syntax=docker/dockerfile:1.14-labs\n"
    else:
        run_instruction = "RUN"
        syntax_directive = ""
    return syntax_directive + template.replace("@RUN@", run_instruction)


def prepare_docker_builder(engine_command, builder_name):
    inspection = subprocess.run(
        engine_command + ["buildx", "inspect", builder_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if inspection.returncode != 0:
        subprocess.run(
            engine_command
            + [
                "buildx",
                "create",
                "--name",
                builder_name,
                "--driver",
                "docker-container",
                "--buildkitd-flags",
                "--allow-insecure-entitlement security.insecure",
            ],
            check=True,
        )


def record_builder_id(engine_command, builder_name, cidfile):
    # Start the daemon so its container ID is available before building stages.
    subprocess.run(
        engine_command + ["buildx", "inspect", "--bootstrap", builder_name],
        check=True,
    )
    container_id = subprocess.check_output(
        engine_command
        + ["inspect", "--format", "{{.Id}}", f"buildx_buildkit_{builder_name}0"],
        text=True,
    ).strip()
    cidfile.parent.mkdir(parents=True, exist_ok=True)
    cidfile.write_text(container_id + "\n")


def build_command(
    build,
    *,
    stage,
    tag,
    import_remote_cache=True,
):
    command = list(build.engine_command)
    if build.engine_name == "docker":
        command += [
            "buildx",
            "build",
            "--pull",
            "--builder",
            build.builder_name,
            "--allow",
            "security.insecure",
            "--progress=plain",
        ]
        if build.cache_scope:
            if import_remote_cache:
                command += [
                    "--cache-from",
                    f"type=gha,version=2,scope={build.cache_scope}",
                ]
            command += [
                "--cache-to",
                f"type=gha,version=2,scope={build.cache_scope},mode=max,ignore-error=true",
            ]
        if tag:
            command += ["--load", "-t", tag]
        else:
            command += ["--output=type=cacheonly"]
    else:
        command += [
            "build",
            "--pull=always",
            "--layers",
            "--security-opt=seccomp=unconfined",
            "--security-opt=apparmor=unconfined",
            "--security-opt=label=disable",
        ]
        if tag:
            command += ["-t", tag]
    command += [
        "-f",
        str(build.dockerfile),
        "--target",
        stage,
        "--build-arg",
        f"ARCH={build.guest.architecture}",
        "--build-arg",
        f"BUILD_MIRROR_MODE={build.guest.mirror_mode}",
        "--build-arg",
        f"CACHE_EPOCH={build.guest.cache_epoch}",
        str(REPO),
    ]
    return command


def run_stage(build, *, stage, tag):
    start = time.monotonic()
    print(f"=== rootfs stage {stage}: start ===", flush=True)
    # BuildKit does not reliably distinguish cache import errors from build
    # failures. Retry once without the importer; keep exporting the cache.
    attempts = (True, False) if build.cache_scope else (False,)
    for import_remote_cache in attempts:
        if build.cache_scope and not import_remote_cache:
            print(
                "Build/cache import failed; retrying using local layers only",
                file=sys.stderr,
                flush=True,
            )
        command = build_command(
            build,
            stage=stage,
            tag=tag,
            import_remote_cache=import_remote_cache,
        )
        print(shlex.join(command), flush=True)
        status = subprocess.run(command, check=False).returncode
        if status == 0 or status in INTERRUPTED_STATUSES:
            break

    elapsed = time.monotonic() - start
    print(
        f"=== rootfs stage {stage}: status={status}, seconds={elapsed:.1f} ===",
        flush=True,
    )
    if status != 0:
        raise SystemExit(status)


def stages_through(target):
    if target == "exporter":
        return (*STAGES, "exporter")
    return STAGES[: STAGES.index(target) + 1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("docker", "podman"), required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--target", choices=(*STAGES, "exporter"), default="configured")
    parser.add_argument("--tag", default="local/101strap:rootfs")
    parser.add_argument(
        "--builder-cidfile",
        type=Path,
        help="Write the Docker builder container ID to this file for cleanup",
    )
    args = parser.parse_args()
    if args.render:
        print(render(args.engine), end="")
        return
    if args.builder_cidfile and args.engine != "docker":
        parser.error("--builder-cidfile requires Docker")

    config = read_guest_config()
    cache_mode = os.environ.get("CONTAINER_CACHE", "local")
    if cache_mode not in ("local", "gha"):
        parser.error("CONTAINER_CACHE must be local, or gha with Docker")
    use_remote_cache = cache_mode == "gha"
    cache_scope = None
    if use_remote_cache:
        if args.engine != "docker":
            parser.error("CONTAINER_CACHE must be local, or gha with Docker")
        for name in ("ACTIONS_RUNTIME_TOKEN", "ACTIONS_RESULTS_URL"):
            if not os.environ.get(name):
                parser.error(f"{name} must be exposed to use the Actions cache")
        cache_scope = (
            f"101strap-v1-{os.uname().machine}"
            f"-{config.architecture}-{config.mirror_mode}"
        )

    engine_command = [args.engine]
    builder_name = os.environ.get("BUILDX_BUILDER", "101strap")
    if args.engine == "docker":
        prepare_docker_builder(engine_command, builder_name)
        if args.builder_cidfile:
            record_builder_id(engine_command, builder_name, args.builder_cidfile)

    # Keep the repository as the build context so stage-specific COPY inputs
    # determine cache invalidation, regardless of the temporary recipe path.
    with tempfile.TemporaryDirectory(prefix="101strap-recipe-") as directory:
        dockerfile = Path(directory) / "Dockerfile"
        dockerfile.write_text(render(args.engine))
        build = BuildConfig(
            engine_name=args.engine,
            engine_command=engine_command,
            dockerfile=dockerfile,
            guest=config,
            builder_name=builder_name,
            cache_scope=cache_scope,
        )
        for stage in stages_through(args.target):
            run_stage(
                build,
                stage=stage,
                tag=args.tag if stage == args.target else None,
            )


if __name__ == "__main__":
    main()
