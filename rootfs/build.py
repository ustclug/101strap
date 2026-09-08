"""Build cached guest stages with Docker BuildKit or rootful Podman."""

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
    tools = (REPO / "Dockerfile").read_text().split("\nFROM image AS exporter")[0]
    template = (REPO / "rootfs/Dockerfile.in").read_text()
    if engine_name == "docker":
        run_instruction = "RUN --security=insecure"
        syntax_directive = "# syntax=docker/dockerfile:1.14-labs\n"
    else:
        run_instruction = "RUN"
        syntax_directive = ""
    recipe = template.replace("@TOOLS@", tools.rstrip())
    return syntax_directive + recipe.replace("@RUN@", run_instruction)


def engine_command_for(engine_name, *, use_remote_cache):
    command = []
    if os.geteuid() != 0:
        command.append("sudo")
        if use_remote_cache:
            command.append("--preserve-env=ACTIONS_RUNTIME_TOKEN,ACTIONS_RESULTS_URL")
    return command + [engine_name]


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

    runner_temp = os.environ.get("RUNNER_TEMP")
    if runner_temp:
        # CI cleanup needs the exact disposable daemon ID before stages start.
        subprocess.run(
            engine_command + ["buildx", "inspect", "--bootstrap", builder_name],
            check=True,
        )
        container_id = subprocess.check_output(
            engine_command
            + [
                "inspect",
                "--format",
                "{{.Id}}",
                f"buildx_buildkit_{builder_name}0",
            ],
            text=True,
        ).strip()
        log_directory = Path(runner_temp) / "101strap"
        log_directory.mkdir(parents=True, exist_ok=True)
        (log_directory / "buildkit.cid").write_text(container_id + "\n")


def build_command(
    *,
    engine_name,
    engine_command,
    dockerfile,
    stage,
    config,
    tag,
    builder_name,
    cache_scope,
    import_remote_cache=True,
):
    command = list(engine_command)
    if engine_name == "docker":
        command += [
            "buildx",
            "build",
            "--builder",
            builder_name,
            "--allow",
            "security.insecure",
            "--progress=plain",
        ]
        if cache_scope:
            if import_remote_cache:
                command += ["--cache-from", f"type=gha,version=2,scope={cache_scope}"]
            command += [
                "--cache-to",
                f"type=gha,version=2,scope={cache_scope},mode=max,ignore-error=true",
            ]
        if tag:
            command += ["--load", "-t", tag]
        else:
            command += ["--output=type=cacheonly"]
    else:
        command += [
            "build",
            "--layers",
            "--cap-add=SYS_ADMIN",
            "--cap-add=MKNOD",
            "--security-opt=seccomp=unconfined",
            "--security-opt=label=disable",
        ]
        if tag:
            command += ["-t", tag]
    command += [
        "-f",
        str(dockerfile),
        "--target",
        stage,
        "--build-arg",
        f"ARCH={config.architecture}",
        "--build-arg",
        f"BUILD_MIRROR_MODE={config.mirror_mode}",
        "--build-arg",
        f"CACHE_EPOCH={config.cache_epoch}",
        str(REPO),
    ]
    return command


def run_stage(
    *,
    stage,
    cache_scope,
    engine_name,
    engine_command,
    dockerfile,
    config,
    tag,
    builder_name,
):
    start = time.monotonic()
    print(f"=== rootfs stage {stage}: start ===", flush=True)
    command = build_command(
        stage=stage,
        cache_scope=cache_scope,
        engine_name=engine_name,
        engine_command=engine_command,
        dockerfile=dockerfile,
        config=config,
        tag=tag,
        builder_name=builder_name,
    )
    print(shlex.join(command), flush=True)
    status = subprocess.run(command, check=False).returncode

    should_retry = status != 0 and cache_scope and status not in INTERRUPTED_STATUSES
    if should_retry:
        # BuildKit does not reliably distinguish cache import errors from build
        # failures. Retry once without the importer; keep exporting the cache.
        print(
            "Build/cache import failed; retrying using local layers only",
            file=sys.stderr,
            flush=True,
        )
        command = build_command(
            stage=stage,
            cache_scope=cache_scope,
            engine_name=engine_name,
            engine_command=engine_command,
            dockerfile=dockerfile,
            config=config,
            tag=tag,
            builder_name=builder_name,
            import_remote_cache=False,
        )
        print(shlex.join(command), flush=True)
        status = subprocess.run(command, check=False).returncode

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
    args = parser.parse_args()
    if args.render:
        print(render(args.engine), end="")
        return

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

    engine_command = engine_command_for(args.engine, use_remote_cache=use_remote_cache)
    builder_name = os.environ.get("BUILDX_BUILDER", "101strap")
    if args.engine == "docker":
        prepare_docker_builder(engine_command, builder_name)

    # Keep the repository as the build context so stage-specific COPY inputs
    # determine cache invalidation, regardless of the temporary recipe path.
    with tempfile.TemporaryDirectory(prefix="101strap-recipe-") as directory:
        dockerfile = Path(directory) / "Dockerfile"
        dockerfile.write_text(render(args.engine))
        for stage in stages_through(args.target):
            run_stage(
                stage=stage,
                engine_name=args.engine,
                engine_command=engine_command,
                dockerfile=dockerfile,
                config=config,
                tag=args.tag if stage == args.target else None,
                builder_name=builder_name,
                cache_scope=cache_scope,
            )


if __name__ == "__main__":
    main()
