import json
import tempfile
import unittest
from pathlib import Path

from ssdbench.run_matrix import ConfigurationError, build_fio_command, load_config


class RunnerTests(unittest.TestCase):
    def test_build_fio_command_is_deterministic(self):
        command = build_fio_command(
            target="/dev/nvme0n1",
            name="mixed",
            workload={"rw": "randrw", "rwmixread": 70, "bs": "4k", "iodepth": 32},
            defaults={
                "ioengine": "libaio",
                "direct": True,
                "group_reporting": True,
                "percentile_list": [50.0, 99.0, 99.9],
            },
            profile={"runtime_seconds": 60, "ramp_seconds": 10},
            size_bytes=1024**3,
            output=Path("result.json"),
        )
        self.assertIn("--randrepeat=1", command)
        self.assertIn("--allrandrepeat=1", command)
        self.assertIn("--rwmixread=70", command)
        self.assertIn("--percentile_list=50.0:99.0:99.9", command)
        self.assertIn("--output=result.json", command)

    def test_unknown_workload_is_rejected(self):
        payload = {
            "schema_version": 1,
            "profiles": {
                "bad": {
                    "runtime_seconds": 1,
                    "ramp_seconds": 0,
                    "repetitions": 1,
                    "target_fraction": 0.5,
                    "precondition_rounds": 0,
                    "workloads": ["missing"],
                }
            },
            "workloads": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                load_config(path, "bad")


if __name__ == "__main__":
    unittest.main()

