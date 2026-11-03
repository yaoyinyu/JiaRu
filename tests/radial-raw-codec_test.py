"""无损RAW捕获拒绝坐标漂移、身份替换与覆盖。"""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np

spec = importlib.util.spec_from_file_location('codec_test', Path(__file__).resolve().parents[1] /
                                             'model/training/radial-raw-codec.py')
codec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codec)


class CodecTests(unittest.TestCase):
    def arrays(self):
        rng = np.random.default_rng(17)
        radius = rng.uniform(0, 40, 32).astype(np.float32)
        bins = rng.integers(0, 32, (19, 23), dtype=np.int32)
        distance = rng.uniform(0, 50, bins.shape).astype(np.float32)
        presence = np.array(-.127, np.float32)
        return radius[bins] - distance, presence, radius, bins, distance

    def test_exact_roundtrip_and_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'raw.npz'
            mask, presence, radius, bins, distance = self.arrays()
            codec.save(path, mask, presence, radius, bins, distance, {'candidate': 3})
            rebuilt = codec.read(path, bins, distance, {'candidate': 3})
            for left, right in zip((mask, presence, radius), rebuilt, strict=True):
                self.assertEqual(left.tobytes(), right.tobytes())
            with self.assertRaises(FileExistsError):
                codec.save(path, mask, presence, radius, bins, distance, {'candidate': 3})

    def test_coordinate_and_identity_changes_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'raw.npz'
            mask, presence, radius, bins, distance = self.arrays()
            codec.save(path, mask, presence, radius, bins, distance, {'candidate': 3})
            with self.assertRaises(ValueError):
                codec.read(path, bins, distance + np.float32(1), {'candidate': 3})
            with self.assertRaises(ValueError):
                codec.read(path, bins, distance, {'candidate': 4})

    def test_inexact_output_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'raw.npz'
            mask, presence, radius, bins, distance = self.arrays()
            mask[0, 0] = np.nextafter(mask[0, 0], np.float32(np.inf))
            with self.assertRaises(ValueError):
                codec.save(path, mask, presence, radius, bins, distance, {})
            self.assertFalse(path.exists())

    def test_nan_and_dtype_rejected(self):
        mask, presence, radius, bins, distance = self.arrays()
        with self.assertRaises(ValueError):
            codec.save('must-not-exist.npz', mask, presence.astype(np.float64), radius, bins, distance, {})
        radius[0] = np.nan
        with self.assertRaises(ValueError):
            codec.save('must-not-exist.npz', mask, presence, radius, bins, distance, {})


if __name__ == '__main__':
    unittest.main()
