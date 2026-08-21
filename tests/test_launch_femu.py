import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "launch_femu.sh"


class LaunchFemuTests(unittest.TestCase):
    def test_cloud_init_seed_is_attached_read_only(self):
        completed = subprocess.run(
            [
                str(LAUNCHER),
                "--build-dir",
                "/tmp/femu-build",
                "--image",
                "/tmp/guest.qcow2",
                "--cloud-init-seed",
                "/tmp/seed.iso",
                "--dry-run",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn(
            "file=/tmp/seed.iso,if=virtio,format=raw,readonly=on",
            completed.stdout.replace("\\,", ","),
        )

    def test_cloud_init_seed_must_be_absolute(self):
        completed = subprocess.run(
            [
                str(LAUNCHER),
                "--build-dir",
                "/tmp/femu-build",
                "--image",
                "/tmp/guest.qcow2",
                "--cloud-init-seed",
                "seed.iso",
                "--dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("--cloud-init-seed must be an absolute path", completed.stderr)


if __name__ == "__main__":
    unittest.main()
