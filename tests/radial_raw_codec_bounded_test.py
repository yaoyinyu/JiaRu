import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'model/training' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old = load('original_codec', 'radial-raw-codec.py')
new = load('bounded_codec', 'radial-raw-codec-bounded.py')


class BoundedRawTest(unittest.TestCase):
    def test_original_metadata_and_decoded_heads_remain_byte_exact(self):
        rng = np.random.default_rng(41)
        radius = rng.normal(size=2048).astype(np.float32)
        bins = rng.integers(0, 2048, size=(67, 131), dtype=np.int32)
        distance = rng.normal(size=bins.shape).astype(np.float32)
        presence = np.array(.125, dtype=np.float32)
        identity = dict(ordinal=1, split='train')
        for view in [np.s_[:, :], np.s_[:, ::2]]:
            b, d = bins[view], distance[view]
            mask = radius[b] - d
            with tempfile.TemporaryDirectory() as tmp:
                original = old.save(Path(tmp) / 'old.npz', mask, presence, radius, b, d, identity)
                bounded = new.save(Path(tmp) / 'new.npz', mask, presence, radius, b, d, identity)
                self.assertEqual(original, bounded)
                for a, actual in zip(old.read(Path(tmp) / 'old.npz', b, d, identity), old.read(Path(tmp) / 'new.npz', b, d, identity)):
                    self.assertEqual(a.dtype, actual.dtype)
                    self.assertEqual(a.tobytes(), actual.tobytes())

    def test_signed_zero_mismatch_is_rejected_before_output_creation(self):
        radius = np.zeros(4, np.float32)
        bins = np.zeros((32, 4), np.int32)
        distance = np.zeros_like(bins, dtype=np.float32)
        mask = np.zeros_like(distance)
        mask[17, 2] = -0.0
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.npz'
            with self.assertRaisesRegex(ValueError, 'byte reconstruction'):
                new.save(path, mask, np.array(0, np.float32), radius, bins, distance, {})
            self.assertFalse(path.exists())

    def test_nonfinite_and_overwrite_are_rejected(self):
        radius = np.zeros(4, np.float32)
        bins = np.zeros((32, 4), np.int32)
        distance = np.zeros_like(bins, dtype=np.float32)
        mask = np.zeros_like(distance)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'one.npz'
            new.save(path, mask, np.array(0, np.float32), radius, bins, distance, {})
            with self.assertRaises(FileExistsError):
                new.save(path, mask, np.array(0, np.float32), radius, bins, distance, {})
            distance[-1, -1] = np.nan
            with self.assertRaises(ValueError):
                new.save(Path(tmp) / 'bad.npz', mask, np.array(0, np.float32), radius, bins, distance, {})


if __name__ == '__main__':
    unittest.main()
