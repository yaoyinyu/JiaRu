import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec = importlib.util.spec_from_file_location('dedup', Path(__file__).resolve().parents[1] / 'model/training/audit-saved-proposal-mask-dedup.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class DedupTests(unittest.TestCase):
    def test_duplicate_before_cap_preserves_low_confidence_distinct_nail(self):
        masks = np.zeros((12, 40, 40), bool)
        for i in range(10):
            masks[i, i * 3:i * 3 + 2, 1:3] = True
        masks[10] = masks[0]
        masks[11, 32:34, 1:3] = True
        confidence = [.99, .98, .97, .96, .95, .94, .93, .92, .91, .7, .8, .6]
        selected, all_kept, events = m.select_masks(confidence, masks)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(all_kept), 11)
        self.assertIn(9, selected)
        self.assertNotIn(10, selected)

    def test_more_complete_close_score_replaces_same_slot(self):
        masks = np.zeros((2, 10, 10), bool)
        masks[0, 1:5, 1:5] = True
        masks[1, 1:6, 1:6] = True
        selected, _, events = m.select_masks([.9, .8], masks)
        self.assertEqual(selected, [1])
        self.assertTrue(events[0]['replacementByExistingRule'])

    def test_more_complete_far_score_does_not_replace(self):
        masks = np.zeros((2, 10, 10), bool)
        masks[0, 1:5, 1:5] = True
        masks[1, 1:6, 1:6] = True
        self.assertEqual(m.select_masks([.9, .7], masks)[0], [0])

    def test_nearby_distinct_masks_not_suppressed(self):
        masks = np.zeros((2, 10, 10), bool)
        masks[0, 1:5, 1:4] = True
        masks[1, 1:5, 4:7] = True
        selected, _, events = m.select_masks([.9, .8], masks)
        self.assertEqual(selected, [0, 1])
        self.assertEqual(events, [])


if __name__ == '__main__':
    unittest.main()
