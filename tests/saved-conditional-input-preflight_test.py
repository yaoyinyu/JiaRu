import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec = importlib.util.spec_from_file_location('preflight', Path(__file__).resolve().parents[1] / 'model/training/audit-saved-conditional-input-preflight.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PreflightTests(unittest.TestCase):
    def test_confidence_cap_does_not_preserve_low_rank_truth_automatically(self):
        self.assertEqual(m.capped_indices([.9] * 10 + [.8, .7, .6], 10), list(range(10)))

    def test_confidence_order_and_stable_ties(self):
        self.assertEqual(m.capped_indices([.4, .7, .7, .3], 2), [1, 2])

    def test_cap_keeps_small_inventory(self):
        self.assertEqual(m.capped_indices([.8, .9], 10), [1, 0])

    def test_ambiguous_prompt_tie_is_failure(self):
        self.assertFalse(m.seed_identity([20, 20], 0)['strictlyTargetDominant'])

    def test_target_dominance_is_not_mask_iou_pass(self):
        self.assertTrue(m.seed_identity([21, 20], 0)['strictlyTargetDominant'])
        self.assertFalse(m.seed_identity([0, 0], 0)['strictlyTargetDominant'])

    def test_marker_halo_edge_touch_and_overlap(self):
        self.assertEqual(m.overlap_area([0, 0, 10, 10], [10, 0, 20, 10]), 0)
        self.assertEqual(m.overlap_area([0, 0, 11, 10], [10, 0, 20, 10]), 10)

    def test_pack_same_candidate_condition(self):
        rgb = np.zeros((384, 384, 3), np.uint8)
        seed = np.zeros((384, 384), np.uint8)
        seed[11, 12] = 255
        packed = m.pack_input(rgb, seed)
        self.assertEqual(packed.dtype, np.float32)
        self.assertEqual(packed[3].sum(), 1)
        self.assertEqual(packed[3, 11, 12], 1)
        self.assertEqual(packed[0, 0, 0], np.float32(-.485 / .229))

    def test_nonbinary_seed_rejected(self):
        rgb = np.zeros((384, 384, 3), np.uint8)
        seed = np.ones((384, 384), np.uint8)
        with self.assertRaisesRegex(ValueError, 'pixel contract'):
            m.pack_input(rgb, seed)


if __name__ == '__main__':
    unittest.main()
