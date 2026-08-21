import unittest
from pathlib import Path

from scripts.benchmark_parser import percentile, run


FIXTURE = Path(__file__).parent / "fixtures" / "mixed.fio.json"


class BenchmarkParserTests(unittest.TestCase):
    def test_percentile_uses_bounded_nearest_rank(self):
        self.assertEqual(percentile([40, 10, 30, 20], 0.95), 40)

    def test_run_reports_positive_timings(self):
        result = run(FIXTURE, iterations=5, warmup=1)

        self.assertEqual(result["measurement_scope"], "host-side fio JSON parsing")
        self.assertEqual(result["iterations"], 5)
        self.assertGreater(result["elapsed_ns_per_parse"]["median"], 0)


if __name__ == "__main__":
    unittest.main()
