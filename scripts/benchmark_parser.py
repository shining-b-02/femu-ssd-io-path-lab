#!/usr/bin/env python3
"""Measure the host-side fio JSON parser without claiming SSD performance."""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ssdbench.analyze import parse_fio_result


def percentile(values: list[int], percentile_value: float) -> int:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * percentile_value) - 1))
    return ordered[index]


def run(input_path: Path, iterations: int, warmup: int) -> dict[str, object]:
    if iterations < 1 or warmup < 0:
        raise ValueError("iterations must be positive and warmup must be non-negative")

    for _ in range(warmup):
        parse_fio_result(input_path)

    elapsed_ns: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        parse_fio_result(input_path)
        elapsed_ns.append(time.perf_counter_ns() - started)

    return {
        "schema_version": 1,
        "measurement_scope": "host-side fio JSON parsing",
        "fixture": str(input_path),
        "iterations": iterations,
        "warmup_iterations": warmup,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "elapsed_ns_per_parse": {
            "median": int(statistics.median(elapsed_ns)),
            "p95": percentile(elapsed_ns, 0.95),
            "maximum": max(elapsed_ns),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=10000)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run(args.input, args.iterations, args.warmup)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
