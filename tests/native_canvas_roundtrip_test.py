"""独立原图位置、空候选、尾部位与非有限拒绝门。"""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location('canvas_tested', Path(__file__).resolve().parents[1]/'model/training/audit-native-canvas-roundtrip.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class CanvasTests(unittest.TestCase):
    def test_literal_edge_controls_and_full_tail(self):
        for row in m.controls():
            actual = m.canvas(np.array(row['logits'], np.float32).reshape(row['nativeSize']),
                              row['presence'], row['sourceSize'], row['cropBox'])
            self.assertEqual(np.flatnonzero(actual).tolist(), row['expectedIndices'])
            self.assertTrue(np.array_equal(m.unpack(m.pack(actual), row['sourceSize']), actual))

    def test_negative_presence_rejects_only_this_candidate(self):
        logits = np.ones((2, 3), np.float32)
        actual = m.canvas(logits, -1e-30, [7, 5], [2, 1, 5, 3])
        self.assertEqual(actual.shape, (5, 7))
        self.assertFalse(actual.any())
        self.assertTrue(logits.any())

    def test_nonfinite_small_head_or_mask_is_rejected(self):
        logits = np.ones((2, 3), np.float32)
        for p in [float('nan'), float('inf')]:
            with self.assertRaisesRegex(ValueError, 'finite'):
                m.canvas(logits, p, [7, 5], [2, 1, 5, 3])
        logits[0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, 'finite'):
            m.canvas(logits, -1, [7, 5], [2, 1, 5, 3])

    def test_invalid_translation_and_nonzero_unused_bits_rejected(self):
        with self.assertRaisesRegex(ValueError, 'geometry'):
            m.canvas(np.ones((2, 3), np.float32), 0, [7, 5], [6, 1, 9, 3])
        with self.assertRaisesRegex(ValueError, 'tail bits'):
            m.unpack(bytes([0, 128]), [5, 3])


if __name__ == '__main__':
    unittest.main()
