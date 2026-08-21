import json
import struct
import tempfile
import unittest
from pathlib import Path

from ssdbench.analyze import (
    aggregate,
    collect_rows,
    parse_fio_result,
    summarize_variability,
    write_bar_svg,
    write_csv,
    write_markdown,
)


FIXTURE = Path(__file__).parent / "fixtures" / "mixed.fio.json"


class AnalyzeTests(unittest.TestCase):
    def test_parse_mixed_workload(self):
        metrics = parse_fio_result(FIXTURE)
        self.assertAlmostEqual(metrics["total_iops"], 100_000.0)
        self.assertAlmostEqual(metrics["total_bw_mib_s"], 390.625)
        self.assertAlmostEqual(metrics["read_p99_us"], 80.0)
        self.assertAlmostEqual(metrics["write_p99_us"], 120.0)
        self.assertAlmostEqual(metrics["worst_p99_us"], 120.0)
        self.assertAlmostEqual(metrics["worst_p999_us"], 240.0)

    def test_aggregate_uses_median(self):
        base = {
            "condition": "page-gc75",
            "mapping": "page",
            "gc_threshold": 75,
            "workload": "randread-4k-qd1",
        }
        rows = []
        for value in (10.0, 20.0, 100.0):
            rows.append(
                {
                    **base,
                    "repetition": 1,
                    **{name: value for name in (
                        "read_iops", "write_iops", "total_iops", "read_bw_mib_s",
                        "write_bw_mib_s", "total_bw_mib_s", "read_p99_us",
                        "write_p99_us", "worst_p99_us", "read_p999_us",
                        "write_p999_us", "worst_p999_us", "host_write_pages",
                        "gc_write_pages", "waf"
                    )},
                }
            )
        summary = aggregate(rows)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["repetitions"], 3)
        self.assertEqual(summary[0]["total_iops"], 20.0)

        variability = summarize_variability(rows)
        self.assertEqual(variability[0]["total_iops_min"], 10.0)
        self.assertEqual(variability[0]["total_iops_median"], 20.0)
        self.assertEqual(variability[0]["total_iops_max"], 100.0)
        self.assertEqual(variability[0]["total_iops_relative_range_percent"], 450.0)

    def test_report_pipeline_from_raw_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            report_dir = root / "report"
            run_dir.mkdir()
            (run_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "condition": "page-gc75",
                        "mapping": "page",
                        "gc_threshold": 75,
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "mixed__r01.fio.json").write_bytes(FIXTURE.read_bytes())
            before = bytearray(512)
            after = bytearray(512)
            struct.pack_into("<I", before, 192, 1000)
            struct.pack_into("<Q", before, 200, 100)
            struct.pack_into("<Q", before, 208, 0)
            struct.pack_into("<I", after, 192, 1250)
            struct.pack_into("<Q", after, 200, 1100)
            struct.pack_into("<Q", after, 208, 250)
            (run_dir / "mixed__r01.waf-before.bin").write_bytes(before)
            (run_dir / "mixed__r01.waf-after.bin").write_bytes(after)

            rows = collect_rows(root)
            summary = aggregate(rows)
            report_dir.mkdir()
            write_csv(report_dir / "summary.csv", summary)
            write_bar_svg(report_dir / "iops.svg", summary, "total_iops", "IOPS", "IOPS")
            write_markdown(report_dir / "REPORT.md", summary)

            self.assertEqual(len(rows), 1)
            self.assertAlmostEqual(rows[0]["waf"], 1.25)
            self.assertTrue((report_dir / "summary.csv").exists())
            self.assertIn("<svg", (report_dir / "iops.svg").read_text(encoding="utf-8"))
            self.assertIn("page-gc75", (report_dir / "REPORT.md").read_text(encoding="utf-8"))

    def test_collect_rows_filters_metadata_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for profile in ("smoke", "full"):
                run_dir = root / profile
                run_dir.mkdir()
                (run_dir / "metadata.json").write_text(
                    json.dumps(
                        {
                            "condition": "page-gc75",
                            "mapping": "page",
                            "gc_threshold": 75,
                            "profile": profile,
                        }
                    ),
                    encoding="utf-8",
                )
                (run_dir / "mixed__r01.fio.json").write_bytes(FIXTURE.read_bytes())

            rows = collect_rows(root, profile="full")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["condition"], "page-gc75")


if __name__ == "__main__":
    unittest.main()
