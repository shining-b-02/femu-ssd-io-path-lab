import struct
import unittest

from ssdbench.analyze import interval_waf
from ssdbench.waf import parse_smart_log


def smart_log(waf_x1000: int, host_pages: int, gc_pages: int) -> bytes:
    data = bytearray(512)
    struct.pack_into("<I", data, 192, waf_x1000)
    struct.pack_into("<Q", data, 200, host_pages)
    struct.pack_into("<Q", data, 208, gc_pages)
    return bytes(data)


class SmartLogTests(unittest.TestCase):
    def test_parse_vendor_fields(self):
        parsed = parse_smart_log(smart_log(1275, 10_000, 2_750))
        self.assertEqual(parsed["waf_x1000"], 1275)
        self.assertEqual(parsed["host_write_pages"], 10_000)
        self.assertEqual(parsed["gc_write_pages"], 2_750)
        self.assertAlmostEqual(parsed["waf"], 1.275)

    def test_rejects_short_log(self):
        with self.assertRaises(ValueError):
            parse_smart_log(b"short")

    def test_interval_waf_uses_counter_deltas(self):
        before = smart_log(1200, 1_000, 200)
        after = smart_log(1250, 2_000, 450)
        parsed = interval_waf(before, after)
        self.assertEqual(parsed["host_write_pages"], 1_000)
        self.assertEqual(parsed["gc_write_pages"], 250)
        self.assertAlmostEqual(parsed["waf"], 1.25)


if __name__ == "__main__":
    unittest.main()

