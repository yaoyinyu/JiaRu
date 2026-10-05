"""ROI几何与一一上限计算的独立反例；不读取证据图片或运行模型。"""
import importlib.util
import unittest
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location('saved_roi', Path(__file__).resolve().parents[1] / 'model/training/analyze-saved-nail-roi-coverage.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class CoverageTests(unittest.TestCase):
    def test_native_rounding_and_clipping(self):
        self.assertEqual(m.crop_box([-0.4, 1.2, 9.4, 12.5], 10, 10, 'native_xyxy_floor_ceil'), (0, 1, 10, 10))
        self.assertIsNone(m.crop_box([12, 1, 14, 3], 10, 10, 'native_xyxy_floor_ceil'))

    def test_impossible_square_rejected(self):
        self.assertIsNone(m.crop_box([0, 0, 80, 30], 100, 100, 'square_context_035'))

    def test_partial_roi_cannot_restore_missing_pixels(self):
        truths = np.zeros((1, 20, 20), bool)
        truths[0, 4:8, 4:8] = True
        _, coverage = m.coverage_matrix(truths, [[4, 4, 6, 8]], 'native_xyxy_floor_ceil')
        self.assertEqual(coverage.tolist(), [[0.5]])
        self.assertFalse(m.oracle_allocation(coverage, np.array([[0.5]]))[0]['completeTruthCoverage'])

    def test_one_large_candidate_cannot_count_as_two_nails(self):
        assignments = m.oracle_allocation(np.ones((2, 1)), np.array([[0.5], [0.4]]))
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0]['truthIndex'], 1)

    def test_nonintersecting_seed_not_effective_candidate(self):
        self.assertEqual(m.oracle_allocation(np.ones((1, 1)), np.zeros((1, 1))), [])

    def test_full_coverage_cardinality_has_priority_over_iou(self):
        coverage = np.array([[1, 1], [1, 0.99]])
        seeds = np.array([[0.99, 0.01], [0.01, 0.99]])
        result = m.oracle_allocation(coverage, seeds)
        self.assertEqual([(x['truthIndex'], x['predictionIndex']) for x in result], [(1, 2), (2, 1)])
        self.assertEqual(sum(x['completeTruthCoverage'] for x in result), 2)

    def test_empty_candidate_inventory(self):
        self.assertEqual(m.oracle_allocation(np.zeros((3, 0)), np.zeros((3, 0))), [])

    def test_native_boundary_shift_and_empty_prediction(self):
        truth = np.zeros((40, 40), bool)
        truth[10:30, 10:30] = True
        shifted = np.roll(truth, 3, axis=1)
        perfect = m.boundary_stats(truth, truth, 2)
        shift = m.boundary_stats(truth, shifted, 2)
        empty = m.boundary_stats(truth, np.zeros_like(truth), 2)
        self.assertEqual(perfect['boundaryF1'], 1)
        self.assertLess(shift['boundaryF1'], 1)
        self.assertEqual(shift['predictionOutsideTruthPixels'], 60)
        self.assertEqual(empty['boundaryF1'], 0)
        self.assertEqual(empty['truthMissingPixels'], 400)


if __name__ == '__main__':
    unittest.main()
