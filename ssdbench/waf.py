"""Read FEMU's write-amplification counters from its NVMe SMART log."""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

SMART_LOG_MIN_SIZE = 216
WAF_X1000_OFFSET = 192
HOST_WRITE_PAGES_OFFSET = 200
GC_WRITE_PAGES_OFFSET = 208


def parse_smart_log(data: bytes) -> dict[str, int | float]:
    """Parse FEMU vendor fields from a binary 512-byte NVMe SMART log."""
    if len(data) < SMART_LOG_MIN_SIZE:
        raise ValueError(
            f"SMART log is {len(data)} bytes; expected at least {SMART_LOG_MIN_SIZE}"
        )
    waf_x1000 = struct.unpack_from("<I", data, WAF_X1000_OFFSET)[0]
    host_write_pages = struct.unpack_from("<Q", data, HOST_WRITE_PAGES_OFFSET)[0]
    gc_write_pages = struct.unpack_from("<Q", data, GC_WRITE_PAGES_OFFSET)[0]
    return {
        "waf_x1000": waf_x1000,
        "waf": waf_x1000 / 1000.0,
        "host_write_pages": host_write_pages,
        "gc_write_pages": gc_write_pages,
    }


def capture_smart_log(device: str, nvme_binary: str = "nvme") -> bytes:
    completed = subprocess.run(
        [nvme_binary, "smart-log", "-o", "binary", device],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if len(completed.stdout) < SMART_LOG_MIN_SIZE:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"nvme-cli returned a short SMART log. stderr={stderr!r}")
    return completed.stdout


def write_capture(data: bytes, binary_path: Path) -> dict[str, Any]:
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    binary_path.write_bytes(data)
    parsed = parse_smart_log(data)
    binary_path.with_suffix(".json").write_text(
        json.dumps(parsed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--device", help="NVMe namespace/controller to query")
    source.add_argument("--binary", type=Path, help="existing binary SMART log")
    parser.add_argument("--save-binary", type=Path)
    args = parser.parse_args()

    data = args.binary.read_bytes() if args.binary else capture_smart_log(args.device)
    parsed = parse_smart_log(data)
    if args.save_binary:
        write_capture(data, args.save_binary)
    print(json.dumps(parsed, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

