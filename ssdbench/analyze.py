"""Aggregate fio JSON and FEMU WAF counters into CSV, Markdown, and SVG."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .waf import parse_smart_log


def _latency_value_us(section: dict[str, Any], percentile: float) -> float:
    for key, divisor in (("clat_ns", 1000.0), ("clat_us", 1.0), ("clat_ms", 0.001)):
        latency = section.get(key, {})
        values = latency.get("percentile", {})
        if not values:
            continue
        numeric = [(float(name), float(value)) for name, value in values.items()]
        _, selected = min(numeric, key=lambda item: abs(item[0] - percentile))
        return selected / divisor
    return 0.0


def parse_fio_result(path: Path) -> dict[str, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    jobs = payload.get("jobs", [])
    if not jobs:
        raise ValueError(f"no fio jobs found in {path}")

    read_iops = sum(float(job.get("read", {}).get("iops", 0)) for job in jobs)
    write_iops = sum(float(job.get("write", {}).get("iops", 0)) for job in jobs)
    read_bw = sum(float(job.get("read", {}).get("bw_bytes", 0)) for job in jobs)
    write_bw = sum(float(job.get("write", {}).get("bw_bytes", 0)) for job in jobs)
    read_p99 = max((_latency_value_us(job.get("read", {}), 99.0) for job in jobs), default=0.0)
    write_p99 = max((_latency_value_us(job.get("write", {}), 99.0) for job in jobs), default=0.0)
    read_p999 = max((_latency_value_us(job.get("read", {}), 99.9) for job in jobs), default=0.0)
    write_p999 = max((_latency_value_us(job.get("write", {}), 99.9) for job in jobs), default=0.0)
    active_p99 = [value for value in (read_p99, write_p99) if value > 0]
    active_p999 = [value for value in (read_p999, write_p999) if value > 0]
    return {
        "read_iops": read_iops,
        "write_iops": write_iops,
        "total_iops": read_iops + write_iops,
        "read_bw_mib_s": read_bw / 1024**2,
        "write_bw_mib_s": write_bw / 1024**2,
        "total_bw_mib_s": (read_bw + write_bw) / 1024**2,
        "read_p99_us": read_p99,
        "write_p99_us": write_p99,
        "worst_p99_us": max(active_p99, default=0.0),
        "read_p999_us": read_p999,
        "write_p999_us": write_p999,
        "worst_p999_us": max(active_p999, default=0.0),
    }


def interval_waf(before: bytes, after: bytes) -> dict[str, float | int]:
    before_stats = parse_smart_log(before)
    after_stats = parse_smart_log(after)
    host_pages = int(after_stats["host_write_pages"]) - int(before_stats["host_write_pages"])
    gc_pages = int(after_stats["gc_write_pages"]) - int(before_stats["gc_write_pages"])
    if host_pages < 0 or gc_pages < 0:
        raise ValueError("FEMU WAF counters moved backwards")
    waf = (host_pages + gc_pages) / host_pages if host_pages else 1.0
    return {"host_write_pages": host_pages, "gc_write_pages": gc_pages, "waf": waf}


def collect_rows(root: Path, profile: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fio_path in sorted(root.rglob("*.fio.json")):
        if fio_path.name == "precondition.fio.json":
            continue
        metadata_path = fio_path.parent / "metadata.json"
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if profile is not None and metadata.get("profile") != profile:
            continue
        stem = fio_path.name.removesuffix(".fio.json")
        if "__r" not in stem:
            continue
        workload, repetition_text = stem.rsplit("__r", 1)
        before_path = fio_path.parent / f"{stem}.waf-before.bin"
        after_path = fio_path.parent / f"{stem}.waf-after.bin"
        metrics: dict[str, Any] = parse_fio_result(fio_path)
        if before_path.exists() and after_path.exists():
            metrics.update(interval_waf(before_path.read_bytes(), after_path.read_bytes()))
        else:
            metrics.update({"host_write_pages": 0, "gc_write_pages": 0, "waf": 1.0})
        rows.append(
            {
                "condition": metadata["condition"],
                "mapping": metadata.get("mapping", "unknown"),
                "gc_threshold": metadata.get("gc_threshold", "unknown"),
                "workload": workload,
                "repetition": int(repetition_text),
                **metrics,
            }
        )
    return rows


METRIC_FIELDS = [
    "read_iops",
    "write_iops",
    "total_iops",
    "read_bw_mib_s",
    "write_bw_mib_s",
    "total_bw_mib_s",
    "read_p99_us",
    "write_p99_us",
    "worst_p99_us",
    "read_p999_us",
    "write_p999_us",
    "worst_p999_us",
    "host_write_pages",
    "gc_write_pages",
    "waf",
]


def aggregate(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, Any, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (row["condition"], row["mapping"], row["gc_threshold"], row["workload"])
        grouped[key].append(row)
    output: list[dict[str, Any]] = []
    for key, members in sorted(grouped.items()):
        condition, mapping, gc_threshold, workload = key
        item: dict[str, Any] = {
            "condition": condition,
            "mapping": mapping,
            "gc_threshold": gc_threshold,
            "workload": workload,
            "repetitions": len(members),
        }
        for metric in METRIC_FIELDS:
            item[metric] = statistics.median(float(member[metric]) for member in members)
        output.append(item)
    return output


VARIABILITY_METRICS = ["total_iops", "worst_p99_us", "worst_p999_us", "waf"]


def summarize_variability(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, Any, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (row["condition"], row["mapping"], row["gc_threshold"], row["workload"])
        grouped[key].append(row)

    output: list[dict[str, Any]] = []
    for key, members in sorted(grouped.items()):
        condition, mapping, gc_threshold, workload = key
        item: dict[str, Any] = {
            "condition": condition,
            "mapping": mapping,
            "gc_threshold": gc_threshold,
            "workload": workload,
            "repetitions": len(members),
        }
        for metric in VARIABILITY_METRICS:
            values = [float(member[metric]) for member in members]
            median = statistics.median(values)
            item[f"{metric}_min"] = min(values)
            item[f"{metric}_median"] = median
            item[f"{metric}_max"] = max(values)
            item[f"{metric}_relative_range_percent"] = (
                (max(values) - min(values)) / median * 100 if median else 0.0
            )
        output.append(item)
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _nice_max(value: float) -> float:
    if value <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(value))
    normalized = value / magnitude
    nice = 1 if normalized <= 1 else 2 if normalized <= 2 else 5 if normalized <= 5 else 10
    return nice * magnitude


def write_bar_svg(path: Path, rows: list[dict[str, Any]], metric: str, title: str, unit: str) -> None:
    width = max(900, 120 + len(rows) * 68)
    height = 520
    left, right, top, bottom = 90, 30, 70, 150
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_value = _nice_max(max((float(row[metric]) for row in rows), default=0.0) * 1.05)
    bar_slot = plot_width / max(len(rows), 1)
    palette = ["#2563eb", "#0f766e", "#c2410c", "#7c3aed", "#be123c", "#4d7c0f"]
    conditions = {name: index for index, name in enumerate(sorted({row["condition"] for row in rows}))}

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2:.1f}" y="34" text-anchor="middle" font-family="sans-serif" font-size="22" font-weight="700">{html.escape(title)}</text>',
    ]
    for tick in range(6):
        value = max_value * tick / 5
        y = top + plot_height - plot_height * tick / 5
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#e5e7eb"/>')
        parts.append(
            f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11" fill="#4b5563">{value:,.2g}</text>'
        )
    for index, row in enumerate(rows):
        value = float(row[metric])
        bar_height = plot_height * value / max_value
        x = left + index * bar_slot + bar_slot * 0.18
        y = top + plot_height - bar_height
        color = palette[conditions[row["condition"]] % len(palette)]
        label = f"{row['condition']} | {row['workload']}"
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_slot*0.64:.1f}" height="{bar_height:.1f}" rx="2" fill="{color}"/>'
        )
        parts.append(
            f'<text transform="translate({x+bar_slot*0.32:.1f},{top+plot_height+12}) rotate(55)" text-anchor="start" font-family="sans-serif" font-size="10" fill="#374151">{html.escape(label)}</text>'
        )
    parts.extend(
        [
            f'<line x1="{left}" y1="{top+plot_height}" x2="{width-right}" y2="{top+plot_height}" stroke="#111827"/>',
            f'<text x="18" y="{top+plot_height/2:.1f}" transform="rotate(-90 18 {top+plot_height/2:.1f})" text-anchor="middle" font-family="sans-serif" font-size="13">{html.escape(unit)}</text>',
            '</svg>',
        ]
    )
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# FEMU SSD I/O experiment report",
        "",
        "Median values across repetitions. Mixed workloads use the worse active-direction tail latency.",
        "",
        "| Condition | Workload | IOPS | BW (MiB/s) | p99 (us) | p99.9 (us) | WAF |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['condition']} | {row['workload']} | {row['total_iops']:,.1f} | "
            f"{row['total_bw_mib_s']:,.1f} | {row['worst_p99_us']:,.1f} | "
            f"{row['worst_p999_us']:,.1f} | {row['waf']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Figures",
            "",
            "![IOPS](iops.svg)",
            "",
            "![p99 latency](p99-latency.svg)",
            "",
            "![Write amplification](waf.svg)",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--profile",
        help="only aggregate runs whose metadata profile matches this value",
    )
    args = parser.parse_args()

    if args.profile is None:
        profiles = set()
        for metadata_path in args.input.rglob("metadata.json"):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("profile"):
                profiles.add(str(metadata["profile"]))
        if len(profiles) > 1:
            parser.error(
                "multiple result profiles found "
                f"({', '.join(sorted(profiles))}); pass --profile to avoid mixing them"
            )

    raw_rows = collect_rows(args.input, args.profile)
    if not raw_rows:
        detail = f" for profile {args.profile!r}" if args.profile else ""
        parser.error(f"no experiment result files found under {args.input}{detail}")
    summary = aggregate(raw_rows)
    variability = summarize_variability(raw_rows)
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "runs.csv", raw_rows)
    write_csv(args.output / "summary.csv", summary)
    write_csv(args.output / "variability.csv", variability)
    write_bar_svg(args.output / "iops.svg", summary, "total_iops", "IOPS by condition and workload", "IOPS")
    write_bar_svg(
        args.output / "p99-latency.svg",
        summary,
        "worst_p99_us",
        "p99 completion latency",
        "microseconds",
    )
    write_bar_svg(args.output / "waf.svg", summary, "waf", "Interval write amplification", "WAF")
    write_markdown(args.output / "REPORT.md", summary)
    print(f"Wrote report to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
