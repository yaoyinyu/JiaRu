"""整图预测存储、原像素真值与一一ROI诊断的反例测试。"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
import numpy as np
R = Path(__file__).resolve().parents[1]
def load(name, file):
    sp = importlib.util.spec_from_file_location(name, R / 'model/training' / file)
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
eval = load('reviewed_diag_test', 'evaluate-reviewed-stage-a.py')
helper = load('prediction_diag_test', 'run-train-role-marker-sensitivity-probe.py')
roi = load('roi_diag_test', 'analyze-saved-nail-roi-coverage.py')


class Tests(unittest.TestCase):
    def test_native_float_polygons_and_coordinate_pairs_share_same_storage_domain(self):
        source = {'polygons': [[(2.5, 3.5), (8.5, 3.5), (8.5, 9.5), (2.5, 9.5)]], 'size': [12, 14]}
        first = eval.truths(source)
        self.assertEqual(first.shape, (1, 14, 12))
        self.assertEqual(first.dtype, np.bool_)
        source['polygons'] = [[[2.5, 3.5], [8.5, 3.5], [8.5, 9.5], [2.5, 9.5]]]
        self.assertTrue(np.array_equal(first, eval.truths(source)))

    def test_empty_prediction_keeps_all_truths_unmatched(self):
        truth = np.zeros((2, 100, 100), dtype=bool)
        truth[0, 20:30, 20:30] = True; truth[1, 20:30, 50:60] = True
        result = helper.match_masks(np.zeros((0, 100, 100), dtype=bool), truth, .75)
        self.assertEqual(result['missedTruthIndices'], [1, 2])
        self.assertEqual(result['matches'], [])

    def test_large_candidate_roi_cannot_count_twice_for_two_nails(self):
        truth = np.zeros((2, 100, 100), dtype=bool)
        truth[0, 20:30, 20:30] = True; truth[1, 20:30, 50:60] = True
        prediction = np.any(truth, axis=0)[None]
        matched = helper.match_masks(prediction, truth, .75)
        _, coverage = roi.coverage_matrix(truth, np.array([[18, 18, 62, 32]]), 'square_context_035')
        self.assertTrue((coverage == 1).all())
        allocation = roi.oracle_allocation(coverage, np.array(matched['iouMatrix']))
        self.assertEqual(len(allocation), 1)
        self.assertEqual(sum(a['completeTruthCoverage'] for a in allocation), 1)

    def test_prediction_roundtrip_retains_native_binary_masks_and_shapes(self):
        with tempfile.TemporaryDirectory() as folder:
            masks = np.zeros((1, 7, 11), dtype=bool); masks[0, 1:6, 2:9] = True
            ref = helper.save_prediction(Path(folder) / 'prediction.npz', np.array([[2, 1, 9, 6]], dtype=np.float32), np.array([.75], dtype=np.float32), np.zeros(1, dtype=np.float32), masks)
            _, _, _, decoded = helper.load_prediction(ref, [11, 7])
            self.assertTrue(np.array_equal(masks, decoded))
            with self.assertRaises(ValueError): helper.load_prediction(ref, [7, 11])


if __name__ == '__main__': unittest.main()
