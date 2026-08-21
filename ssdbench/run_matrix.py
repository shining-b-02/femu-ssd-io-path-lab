"""Run a guarded fio workload matrix against a FEMU NVMe namespace."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

from .waf import capture_smart_log, write_capture

FEMU_PINNED_REVISION = "39664d2424eaa4ebdcf8400f8973d3ad445644a6"


class ConfigurationError(ValueError):
    pass


def load_config(path: Path, profile_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ConfigurationError("unsupported or missing schema_version")
    try:
        profile = config["profiles"][profile_name]
        workloads = config["workloads"]
    except KeyError as exc:
        raise ConfigurationError(f"missing configuration key: {exc}") from exc
    required = {
        "runtime_seconds",
        "ramp_seconds",
        "repetitions",
        "target_fraction",
        "precondition_rounds",
        "workloads",
    }
    missing = required - profile.keys()
    if missing:
        raise ConfigurationError(f"profile is missing: {sorted(missing)}")
    if not 0 < float(profile["target_fraction"]) <= 1:
        raise ConfigurationError("target_fraction must be in (0, 1]")
    for name in profile["workloads"]:
        if name not in workloads:
            raise ConfigurationError(f"unknown workload: {name}")
    return config, profile


def build_fio_command(
    *,
    target: str,
    name: str,
    workload: dict[str, Any],
    defaults: dict[str, Any],
    profile: dict[str, Any],
    size_bytes: int,
    output: Path,
) -> list[str]:
    command = [
        "fio",
        f"--name={name}",
        f"--filename={target}",
        f"--rw={workload['rw']}",
        f"--bs={workload['bs']}",
        f"--iodepth={int(workload['iodepth'])}",
        f"--ioengine={defaults.get('ioengine', 'libaio')}",
        f"--direct={1 if defaults.get('direct', True) else 0}",
        "--numjobs=1",
        "--time_based=1",
        f"--runtime={int(profile['runtime_seconds'])}",
        f"--ramp_time={int(profile['ramp_seconds'])}",
        f"--size={size_bytes}",
        "--randrepeat=1",
        "--allrandrepeat=1",
        "--norandommap=1",
        f"--group_reporting={1 if defaults.get('group_reporting', True) else 0}",
        "--output-format=json",
        f"--output={output}",
    ]
    percentiles = defaults.get("percentile_list", [50.0, 95.0, 99.0, 99.9])
    command.append("--percentile_list=" + ":".join(str(item) for item in percentiles))
    if "rwmixread" in workload:
        command.append(f"--rwmixread={int(workload['rwmixread'])}")
    return command


def build_precondition_command(
    target: str, size_bytes: int, rounds: int, output: Path, ioengine: str
) -> list[str]:
    return [
        "fio",
        "--name=precondition",
        f"--filename={target}",
        "--rw=randwrite",
        "--bs=4k",
        "--iodepth=32",
        f"--ioengine={ioengine}",
        "--direct=1",
        "--numjobs=1",
        f"--size={size_bytes}",
        f"--loops={rounds}",
        "--randrepeat=1",
        "--allrandrepeat=1",
        "--norandommap=1",
        "--group_reporting=1",
        "--output-format=json",
        f"--output={output}",
    ]


def _lsblk(target: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["lsblk", "-J", "-o", "NAME,TYPE,MOUNTPOINT,MODEL", target],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return json.loads(completed.stdout)


def _flatten_devices(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for device in devices:
        flattened.append(device)
        flattened.extend(_flatten_devices(device.get("children", [])))
    return flattened


def validate_target(target: str, allow_non_femu: bool) -> str:
    if platform.system() != "Linux":
        raise RuntimeError("live raw-device runs are supported only inside the Linux guest")
    if not os.path.exists(target):
        raise RuntimeError(f"target does not exist: {target}")
    mode = os.stat(target).st_mode
    if not stat.S_ISBLK(mode):
        raise RuntimeError(f"target is not a block device: {target}")
    if not os.access(target, os.R_OK | os.W_OK):
        raise RuntimeError(f"target is not readable and writable: {target}")

    tree = _lsblk(target)
    devices = _flatten_devices(tree.get("blockdevices", []))
    mounted = [item.get("name") for item in devices if item.get("mountpoint")]
    if mounted:
        raise RuntimeError(f"target or a child device is mounted: {mounted}")
    model = " ".join(str(item.get("model") or "") for item in devices).strip()
    if "femu" not in model.lower() and not allow_non_femu:
        raise RuntimeError(
            f"device model does not identify as FEMU ({model!r}); refusing destructive I/O"
        )
    return model


def target_size(target: str) -> int:
    completed = subprocess.run(
        ["blockdev", "--getsize64", target],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return int(completed.stdout.strip())


def _git_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def _command_version(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError:
        return None
    first_line = completed.stdout.strip().splitlines()
    return first_line[0] if first_line else None


def _run(command: list[str]) -> None:
    print("+", shlex.join(command), flush=True)
    subprocess.run(command, check=True, env={**os.environ, "LC_ALL": "C"})


def run(args: argparse.Namespace) -> Path | None:
    config, profile = load_config(args.config, args.profile)
    defaults = config.get("defaults", {})
    workloads = config["workloads"]

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.condition):
        raise ConfigurationError("condition must contain only letters, digits, '.', '_' or '-'")
    if not 1 <= args.gc_threshold < 95:
        raise ConfigurationError("gc-threshold must be in [1, 94] for the fixed high threshold 95")

    if args.dry_run:
        dry_size = int(4 * 1024**3 * float(profile["target_fraction"]))
        for workload_name in profile["workloads"]:
            output = Path("<run-dir>") / f"{workload_name}__r01.fio.json"
            command = build_fio_command(
                target=args.target,
                name=workload_name,
                workload=workloads[workload_name],
                defaults=defaults,
                profile=profile,
                size_bytes=dry_size,
                output=output,
            )
            print(shlex.join(command))
        return None

    if not args.confirm_erase_femu_device:
        raise RuntimeError("live run requires --confirm-erase-femu-device")
    for binary in ("fio", "nvme", "lsblk", "blockdev"):
        if shutil.which(binary) is None:
            raise RuntimeError(f"required command not found: {binary}")

    device_model = validate_target(args.target, args.allow_non_femu)
    size_bytes = int(target_size(args.target) * float(profile["target_fraction"]))
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output.resolve() / f"{timestamp}__{args.condition}"
    run_dir.mkdir(parents=True, exist_ok=False)

    metadata = {
        "schema_version": 1,
        "created_at_utc": timestamp,
        "condition": args.condition,
        "mapping": args.mapping,
        "gc_threshold": args.gc_threshold,
        "profile": args.profile,
        "target": args.target,
        "target_model": device_model,
        "target_size_bytes": target_size(args.target),
        "fio_size_bytes": size_bytes,
        "host": {
            "platform": platform.platform(),
            "kernel": platform.release(),
            "python": platform.python_version(),
        },
        "project_git_revision": _git_revision(),
        "expected_femu_revision": FEMU_PINNED_REVISION,
        "tools": {
            "fio": _command_version(["fio", "--version"]),
            "nvme_cli": _command_version(["nvme", "version"]),
        },
        "config": config,
    }
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    precondition_rounds = int(profile["precondition_rounds"])
    if precondition_rounds:
        precondition = build_precondition_command(
            args.target,
            size_bytes,
            precondition_rounds,
            run_dir / "precondition.fio.json",
            defaults.get("ioengine", "libaio"),
        )
        _run(precondition)

    for workload_name in profile["workloads"]:
        for repetition in range(1, int(profile["repetitions"]) + 1):
            stem = f"{workload_name}__r{repetition:02d}"
            before_path = run_dir / f"{stem}.waf-before.bin"
            after_path = run_dir / f"{stem}.waf-after.bin"
            write_capture(capture_smart_log(args.target), before_path)
            command = build_fio_command(
                target=args.target,
                name=workload_name,
                workload=workloads[workload_name],
                defaults=defaults,
                profile=profile,
                size_bytes=size_bytes,
                output=run_dir / f"{stem}.fio.json",
            )
            _run(command)
            write_capture(capture_smart_log(args.target), after_path)

    print(f"Completed run: {run_dir}")
    return run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--mapping", choices=["page", "dftl", "hybrid", "fast"], required=True)
    parser.add_argument("--gc-threshold", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--confirm-erase-femu-device",
        action="store_true",
        help="acknowledge that fio will overwrite the raw FEMU namespace",
    )
    parser.add_argument(
        "--allow-non-femu",
        action="store_true",
        help="expert override; permit destructive I/O on a model not named FEMU",
    )
    return parser.parse_args()


def main() -> int:
    try:
        run(parse_args())
    except (ConfigurationError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
