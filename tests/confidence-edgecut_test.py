"""独立合成控制：穷举最小割、图像弱先验、模型强先验、异常与拒识。"""
import importlib.util
import itertools
from pathlib import Path
import unittest
import numpy as np

s = importlib.util.spec_from_file_location('confidence_edgecut', Path(__file__).resolve().parents[1] / 'model/training/refine-mask-with-edgecut.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)


class ConfidenceEdgeCutTests(unittest.TestCase):
    def test_graph_energy_matches_exhaustive_minimum(self):
        rgb = np.array([[[0, 0, 0], [0, 0, 0], [255, 255, 255]],
                        [[0, 0, 0], [255, 255, 255], [255, 255, 255]]], np.uint8)
        logits = np.array([[-2, .1, 2], [-2, 2, -.1]], np.float32)
        graph, index, _, _ = m.graph(rgb, logits, logits >= 0, radius=1)
        labels, energy = m.cut(graph); n = int((index >= 0).sum())
        def cost(bits):
            side = np.array([*bits, True, False]); rows, cols = graph.nonzero()
            weights = np.asarray(graph[rows, cols]).reshape(-1)
            return int(weights[side[rows] & ~side[cols]].sum())
        self.assertEqual(energy, min(cost(bits) for bits in itertools.product([False, True], repeat=n)))
        self.assertEqual(cost(labels), energy)

    def test_rgb_edges_correct_weak_pixels_without_overruling_strong_prior(self):
        rgb = np.zeros((25, 35, 3), np.uint8); rgb[:, 18:] = 255
        logits = np.full((25, 35), -8, np.float32); logits[:, 18:] = 8
        logits[8:17, 17] = .1  # 跨颜色边的弱误标应去掉。
        actual, status, _ = m.refine(rgb, logits, presence_accepted=True)
        self.assertEqual(status, 'refined'); self.assertFalse(actual[8:17, 17].any())
        self.assertTrue(actual[:, 19:].all()); self.assertFalse(actual[:, :15].any())
        second, _, _ = m.refine(rgb, logits, presence_accepted=True)
        self.assertTrue(np.array_equal(actual, second))

    def test_no_regularization_is_original_decode_and_band_lock(self):
        rng = np.random.default_rng(7)
        rgb = rng.integers(0, 256, (29, 41, 3), dtype=np.uint8)
        logits = np.full((29, 41), -8, np.float32); logits[8:23, 12:30] = 8
        actual, _, _ = m.refine(rgb, logits, presence_accepted=True, weight=0)
        self.assertTrue(np.array_equal(actual, logits >= 0))
        logits[8:10, 12:15] = 0
        logits[6:8, 12:15] = -1e-10
        actual, _, _ = m.refine(rgb, logits, presence_accepted=True, weight=0)
        self.assertTrue(np.array_equal(actual, logits >= 0))
        actual, _, _ = m.refine(rgb, logits, presence_accepted=True, radius=2)
        _, _, inner, outer = m.graph(rgb, logits, logits >= 0, radius=2)
        self.assertTrue(actual[inner].all()); self.assertFalse(actual[~outer].any())

    def test_invalid_raw_is_execution_error_not_rejection(self):
        rgb = np.zeros((12, 13, 3), np.uint8); logits = np.full((12, 13), -1, np.float32)
        actual, status, _ = m.refine(rgb, logits, presence_accepted=True)
        self.assertEqual(status, 'empty'); self.assertFalse(actual.any())
        actual, status, _ = m.refine(rgb, -logits, presence_accepted=False)
        self.assertEqual(status, 'rejected'); self.assertFalse(actual.any())
        logits[0, 0] = np.nan
        with self.assertRaises(ValueError): m.refine(rgb, logits, presence_accepted=False)


if __name__ == '__main__': unittest.main()
